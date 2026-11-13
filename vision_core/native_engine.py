from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import os
import subprocess
import sys
import threading
from typing import Callable


def find_stockfish_binary(explicit_path: str | None = None) -> str | None:
    """Locate stockfish.exe across dev repo, PyInstaller bundle, and install folders."""
    candidates: list[str] = []
    if explicit_path:
        candidates.append(explicit_path)

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(os.path.join(meipass, "assets", "stockfish.exe"))
        candidates.append(os.path.join(meipass, "stockfish.exe"))

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates.append(os.path.join(repo_root, "assets", "stockfish.exe"))

    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    candidates.append(os.path.join(exe_dir, "assets", "stockfish.exe"))
    candidates.append(os.path.join(exe_dir, "stockfish.exe"))

    for env_key in ("LOCALAPPDATA", "APPDATA"):
        base = os.environ.get(env_key)
        if base:
            candidates.append(os.path.join(base, "ChessStealthPro", "stockfish.exe"))
            candidates.append(os.path.join(base, "ChessStealth", "stockfish.exe"))

    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def _format_uci_score(kind: str, val_str: str) -> str:
    try:
        val = int(val_str)
    except ValueError:
        return "+0.0"

    if kind == "mate":
        if val == 0:
            return "M0"
        sign = "+" if val > 0 else "-"
        return f"{sign}M{abs(val)}"

    # Round half-up to 0.1 pawns using integer arithmetic (cp=35 -> +0.4)
    tenths = (abs(val) + 5) // 10
    sign = "-" if val < 0 and tenths > 0 else "+"
    return f"{sign}{tenths // 10}.{tenths % 10}"


def _parse_info_line(line: str) -> tuple[str, str, str, str] | None:
    """Return (move, ponder, depth_str, eval_str) from a UCI info line, else None."""
    tokens = line.split()
    if not tokens or tokens[0] != "info":
        return None
    # Skip Stockfish multipv secondary lines if multipv > 1
    if "multipv" in tokens:
        idx = tokens.index("multipv")
        if idx + 1 < len(tokens) and tokens[idx + 1] != "1":
            return None

    depth_str = ""
    eval_str = ""
    move = ""
    ponder = ""

    i = 1
    n = len(tokens)
    while i < n:
        tok = tokens[i]
        if tok == "depth" and i + 1 < n:
            depth_str = tokens[i + 1]
            i += 2
        elif tok == "score" and i + 2 < n:
            eval_str = _format_uci_score(tokens[i + 1], tokens[i + 2])
            i += 3
        elif tok == "pv" and i + 1 < n:
            move = tokens[i + 1]
            ponder = tokens[i + 2] if i + 2 < n else ""
            break
        else:
            i += 1

    if not move or move == "(none)":
        return None
    return move, ponder, depth_str or "1", eval_str or "+0.0"


@dataclass
class _SearchJob:
    seq_id: int
    board_key: str
    fen: str
    on_update: Callable[[dict], None] | None
    canceled: bool = False
    stop_sent: bool = False
    last_depth: str = "0"
    last_eval: str = "+0.0"
    last_move: str = ""
    last_ponder: str = ""
    last_emitted: tuple[str, str, str] | None = None


class NativeStockfishEngine:
    """Thread-safe native UCI Stockfish runner with FIFO stale-search isolation."""

    def __init__(self, exe_path: str | None = None, threads: int = 2, hash_mb: int = 64):
        self.exe_path = exe_path or find_stockfish_binary()
        self.threads = max(1, int(threads))
        self.hash_mb = max(8, int(hash_mb))
        self._proc = None
        self._reader_thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._uciok_event = threading.Event()
        self._readyok_event = threading.Event()
        self._queue: deque[_SearchJob] = deque()
        self._search_seq = 0
        self._skill = 20
        self._closed = False

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None and not self._closed

    def start(self, timeout: float = 4.0) -> bool:
        with self._lock:
            if self.is_running:
                return True
            exe = self.exe_path or find_stockfish_binary()
            if not exe:
                return False
            self.exe_path = exe
            self._closed = False
            self._uciok_event.clear()
            self._readyok_event.clear()
            self._queue.clear()

            kwargs: dict = {
                "stdin": subprocess.PIPE,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.STDOUT,
                "text": True,
                "encoding": "utf-8",
                "errors": "replace",
                "bufsize": 1,
            }
            if sys.platform == "win32":
                kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)

            try:
                self._proc = subprocess.Popen([exe], **kwargs)
            except Exception:
                self._proc = None
                return False

            self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
            self._reader_thread.start()
            self._write_locked("uci\n")

        if not self._uciok_event.wait(timeout=timeout):
            self.shutdown()
            return False

        with self._lock:
            self._write_locked(
                f"setoption name Threads value {self.threads}\n"
                f"setoption name Hash value {self.hash_mb}\n"
                f"isready\n"
            )

        if not self._readyok_event.wait(timeout=timeout):
            self.shutdown()
            return False
        return True

    def _write_locked(self, data: str) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None:
            return
        try:
            proc.stdin.write(data)
            proc.stdin.flush()
        except Exception:
            pass

    def _reader_loop(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        try:
            for raw_line in proc.stdout:
                line = raw_line.strip()
                if not line:
                    continue
                if line == "uciok":
                    self._uciok_event.set()
                    continue
                if line == "readyok":
                    self._readyok_event.set()
                    continue

                if line.startswith("info "):
                    parsed = _parse_info_line(line)
                    if parsed is None:
                        continue
                    move, ponder, depth_str, eval_str = parsed
                    cb = None
                    payload = None
                    with self._lock:
                        if not self._queue:
                            continue
                        cur = self._queue[0]
                        if cur.canceled or cur.seq_id != self._search_seq:
                            continue
                        cur.last_move = move
                        cur.last_ponder = ponder
                        cur.last_depth = depth_str
                        cur.last_eval = eval_str
                        sig = (move, depth_str, eval_str)
                        if cur.on_update is not None and sig != cur.last_emitted:
                            cur.last_emitted = sig
                            cb = cur.on_update
                            payload = {
                                "board_key": cur.board_key,
                                "fen": cur.fen,
                                "move": move,
                                "ponder": ponder,
                                "depth": depth_str,
                                "eval": eval_str,
                                "final": False,
                            }
                    if cb and payload:
                        try:
                            cb(payload)
                        except Exception:
                            pass
                    continue

                if line.startswith("bestmove "):
                    tokens = line.split()
                    best_mv = tokens[1] if len(tokens) > 1 else ""
                    if best_mv == "(none)":
                        best_mv = ""
                    ponder_mv = ""
                    if len(tokens) >= 4 and tokens[2] == "ponder":
                        ponder_mv = tokens[3]

                    cb = None
                    payload = None
                    with self._lock:
                        if not self._queue:
                            continue
                        finished = self._queue.popleft()
                        if (
                            not finished.canceled
                            and finished.seq_id == self._search_seq
                            and finished.on_update is not None
                        ):
                            cb = finished.on_update
                            payload = {
                                "board_key": finished.board_key,
                                "fen": finished.fen,
                                "move": best_mv or finished.last_move,
                                "ponder": ponder_mv or finished.last_ponder,
                                "depth": finished.last_depth,
                                "eval": finished.last_eval,
                                "final": True,
                            }
                    if cb and payload:
                        try:
                            cb(payload)
                        except Exception:
                            pass
        except Exception:
            pass

    def analyze(
        self,
        fen: str,
        depth: int,
        board_key: str,
        skill: int = 20,
        on_update: Callable[[dict], None] | None = None,
    ) -> int:
        if not self.is_running and not self.start():
            return 0

        clamped_depth = max(1, min(30, int(depth)))
        clamped_skill = max(0, min(20, int(skill)))

        with self._lock:
            self._search_seq += 1
            seq_id = self._search_seq
            cmds: list[str] = []

            need_stop = False
            for job in self._queue:
                job.canceled = True
                if not job.stop_sent:
                    job.stop_sent = True
                    need_stop = True
            if need_stop:
                cmds.append("stop\n")

            if clamped_skill != self._skill:
                self._skill = clamped_skill
                cmds.append(f"setoption name Skill Level value {clamped_skill}\n")

            self._queue.append(
                _SearchJob(
                    seq_id=seq_id,
                    board_key=board_key,
                    fen=fen,
                    on_update=on_update,
                )
            )
            cmds.append(f"position fen {fen}\n")
            cmds.append(f"go depth {clamped_depth}\n")
            self._write_locked("".join(cmds))
            return seq_id

    def stop_search(self) -> None:
        with self._lock:
            need_stop = False
            for job in self._queue:
                job.canceled = True
                if not job.stop_sent:
                    job.stop_sent = True
                    need_stop = True
            if need_stop:
                self._write_locked("stop\n")

    def shutdown(self) -> None:
        with self._lock:
            self._closed = True
            for job in self._queue:
                job.canceled = True
            proc = self._proc
            if proc is not None:
                self._write_locked("stop\nquit\n")

        if proc is not None:
            try:
                proc.wait(timeout=0.5)
            except Exception:
                try:
                    proc.terminate()
                    proc.wait(timeout=0.5)
                except Exception:
                    pass
        if self._reader_thread is not None and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=0.5)
        with self._lock:
            self._proc = None
            self._queue.clear()
