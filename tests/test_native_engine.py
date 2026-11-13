import os
import sys
import threading
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from vision_core.native_engine import NativeStockfishEngine, find_stockfish_binary


class _FakePipeProc:
    """In-memory mock UCI subprocess for testing stale search synchronization."""

    def __init__(self, script_fn):
        self._r_fd, self._w_fd = os.pipe()
        self.stdout = os.fdopen(self._r_fd, "r", encoding="utf-8", buffering=1)
        self._out_writer = os.fdopen(self._w_fd, "w", encoding="utf-8", buffering=1)
        self._in_r_fd, self._in_w_fd = os.pipe()
        self.stdin = os.fdopen(self._in_w_fd, "w", encoding="utf-8", buffering=1)
        self._in_reader = os.fdopen(self._in_r_fd, "r", encoding="utf-8", buffering=1)
        self._alive = True
        self._thread = threading.Thread(target=self._run, args=(script_fn,), daemon=True)
        self._thread.start()

    def _run(self, script_fn):
        try:
            for line in self._in_reader:
                cmd = line.strip()
                script_fn(cmd, self._out_writer)
                if cmd == "quit":
                    break
        except Exception:
            pass
        finally:
            self._alive = False
            try:
                self._out_writer.close()
            except Exception:
                pass

    def poll(self):
        return None if self._alive else 0

    def terminate(self):
        self._alive = False
        try:
            self.stdin.close()
        except Exception:
            pass

    def wait(self, timeout=None):
        return 0


def test_uci_fifo_drops_stale_info_and_bestmove_after_stop(monkeypatch):
    def fake_script(cmd, out):
        if cmd == "uci":
            out.write("id name MockSF\nuciok\n")
        elif cmd == "isready":
            out.write("readyok\n")
        elif cmd == "go depth 10":
            # Stale search leaves an info line before stop drains bestmove
            out.write("info depth 3 score cp 12 pv a2a3 a7a6\n")
        elif cmd == "stop":
            # Old search bestmove arrives BEFORE next search outputs its move
            out.write("bestmove a2a3\n")
        elif cmd == "go depth 8":
            out.write("info depth 4 score cp 35 pv e2e4 e7e5\n")
            out.write("bestmove e2e4 ponder e7e5\n")

    monkeypatch.setattr(
        "vision_core.native_engine.subprocess.Popen",
        lambda *a, **kw: _FakePipeProc(fake_script),
    )

    eng = NativeStockfishEngine(exe_path="fake_sf.exe")
    assert eng.start() is True
    results = []
    done = threading.Event()

    def on_upd(payload):
        results.append(payload)
        if payload.get("final") and payload.get("board_key") == "k2":
            done.set()

    eng.analyze("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1", 10, "k1", on_update=on_upd)
    eng.analyze("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1", 8, "k2", on_update=on_upd)
    assert done.wait(timeout=2.0)
    eng.shutdown()

    assert all(r["board_key"] == "k2" for r in results), f"Stale k1 update leaked: {results}"
    assert results[-1]["move"] == "e2e4"
    assert results[-1]["ponder"] == "e7e5"
    assert results[-1]["eval"] == "+0.4"


def test_real_stockfish_binary_present_and_fast():
    exe = find_stockfish_binary()
    assert exe is not None and os.path.exists(exe)

    eng = NativeStockfishEngine(exe_path=exe, threads=2, hash_mb=32)
    assert eng.start() is True
    events = []
    done = threading.Event()
    t0 = time.perf_counter()

    def on_upd(payload):
        events.append((time.perf_counter() - t0, payload))
        if payload.get("final"):
            done.set()

    try:
        eng.analyze("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1", 8, "start", skill=20, on_update=on_upd)
        assert done.wait(timeout=3.0), "Real stockfish.exe timed out on depth 8"
    finally:
        eng.shutdown()

    assert len(events) >= 1
    first_dt_ms = events[0][0] * 1000.0
    final_move = events[-1][1]["move"]
    assert len(final_move) >= 4
    assert first_dt_ms < 400.0
