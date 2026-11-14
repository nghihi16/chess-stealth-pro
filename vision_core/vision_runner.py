from __future__ import annotations

import threading
import time
from typing import Callable

from vision_core.board_detector import BoardBounds, BoardDetector, capture_screen_bgr
from vision_core.chess_rules import ChessBoardState, parse_sq, piece_side, sq_to_screen_rc
from vision_core.native_engine import NativeStockfishEngine


class VisionRunner:
    """Real-time background screen-vision + native Stockfish coordinator."""

    def __init__(
        self,
        arrow_state: dict,
        engine: NativeStockfishEngine | None = None,
        detector: BoardDetector | None = None,
        capture_fn: Callable | None = None,
        browser_detect_fn: Callable[[], dict | None] | None = None,
        dpr_fn: Callable[[int], float] | None = None,
        on_repaint: Callable[[], None] | None = None,
        poll_interval_s: float = 0.07,
    ):
        self.arrow_state = arrow_state
        self.engine = engine or NativeStockfishEngine()
        self.owns_engine = engine is None
        self.detector = detector or BoardDetector()
        self.capture_fn = capture_fn or capture_screen_bgr
        self.browser_detect_fn = browser_detect_fn or (lambda: None)
        self.dpr_fn = dpr_fn or (lambda _hwnd: 1.0)
        self.on_repaint = on_repaint
        self.poll_interval_s = max(0.02, float(poll_interval_s))

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

        self._active_board_key: str = ""
        self._last_req_sig: tuple | None = None
        self._active_bounds: BoardBounds | None = None
        self._active_flipped: bool = False
        self._active_dpr: float = 1.0
        self._active_fen: str = ""
        self._last_drawn_arrow_px: tuple[float, float, float, float, float] | None = None
        self._cached_browser: dict | None = None
        self._cached_dpr: float = 1.0
        self._last_browser_check_ts: float = 0.0
        self._no_board_streak: int = 0

    def _extension_is_fresh(self, now: float | None = None) -> bool:
        t = time.time() if now is None else now
        last_ping = float(self.arrow_state.get("last_ping", 0.0) or 0.0)
        return (t - last_ping) < 3.5

    def _emit_repaint(self) -> None:
        if self.on_repaint is not None:
            try:
                self.on_repaint()
            except Exception:
                pass

    def _clear_vision_arrow_locked(self, status: str | None = None) -> bool:
        had_vision = bool(self.arrow_state.get("vision_active", False))
        was_shown = bool(self.arrow_state.get("show", False))
        if status is not None:
            self.arrow_state["vision_status"] = status
        changed = False
        if had_vision and was_shown:
            self.arrow_state["show"] = False
            changed = True
        if status in ("disabled", "yielded", "waiting") and had_vision:
            self.arrow_state["vision_active"] = False
            changed = True
        self._last_drawn_arrow_px = None
        return changed

    def _should_analyze_turn(self, turn: str, flipped: bool) -> bool:
        pref = str(self.arrow_state.get("side", "auto") or "auto").lower()
        if pref == "both":
            return True
        if pref in ("w", "b"):
            return turn == pref
        my_side = "b" if flipped else "w"
        return turn == my_side

    def _on_engine_update(self, payload: dict) -> None:
        if payload.get("final", True) is False:
            return
        mv = str(payload.get("move") or "")
        if len(mv) < 4:
            return
        with self._lock:
            if not self.arrow_state.get("enabled", True):
                return
            if self._extension_is_fresh():
                return
            if payload.get("board_key") != self._active_board_key:
                return
            bounds = self._active_bounds
            if bounds is None:
                return
            flipped = self._active_flipped
            dpr = max(0.5, float(self._active_dpr))

            try:
                from_sq = parse_sq(mv[:2])
                to_sq = parse_sq(mv[2:4])
            except ValueError:
                return
            fr, fc = sq_to_screen_rc(from_sq, flipped=flipped)
            tr, tc = sq_to_screen_rc(to_sq, flipped=flipped)

            sq_px = bounds.size / 8.0
            fx_px = bounds.x + (fc + 0.5) * sq_px
            fy_px = bounds.y + (fr + 0.5) * sq_px
            tx_px = bounds.x + (tc + 0.5) * sq_px
            ty_px = bounds.y + (tr + 0.5) * sq_px

            piece_char = ""
            fen = str(payload.get("fen") or self._active_fen or "")
            if fen:
                try:
                    piece_char = ChessBoardState.from_fen(fen).board[from_sq] or ""
                except Exception:
                    piece_char = ""

            want_side = piece_side(piece_char) if piece_char else ("b" if flipped else "w")
            if self.detector.is_square_occupied_by(from_sq, want_side) is False:
                self.arrow_state["show"] = False
                self._last_drawn_arrow_px = None
                self._active_board_key = ""
                self._last_req_sig = None
                self.engine.stop_search()
                need_clear = True
            else:
                need_clear = False
                self._last_drawn_arrow_px = (fx_px, fy_px, tx_px, ty_px, sq_px)
                self.arrow_state.update(
                    {
                        "x1": int(round(fx_px / dpr)),
                        "y1": int(round(fy_px / dpr)),
                        "x2": int(round(tx_px / dpr)),
                        "y2": int(round(ty_px / dpr)),
                        "size": max(16, int(round(sq_px / dpr))),
                        "show": True,
                        "move": mv,
                        "ponder": str(payload.get("ponder") or ""),
                        "depth": str(payload.get("depth") or ""),
                        "eval": str(payload.get("eval") or "+0.0"),
                        "piece": piece_char,
                        "flipped": flipped,
                        "auto_aligned": True,
                        "offset_y": 0,
                        "last_seen": time.time(),
                        "vision_active": True,
                        "vision_status": "active",
                    }
                )
        if need_clear or self.arrow_state.get("show", False):
            self._emit_repaint()

    def _current_arrow_px(self, dpr: float) -> tuple[float, float, float, float, float] | None:
        if not self.arrow_state.get("show", False):
            return None
        if self._last_drawn_arrow_px is not None:
            return self._last_drawn_arrow_px
        x1 = float(self.arrow_state.get("x1", 0)) * dpr
        y1 = float(self.arrow_state.get("y1", 0)) * dpr
        x2 = float(self.arrow_state.get("x2", 0)) * dpr
        y2 = float(self.arrow_state.get("y2", 0)) * dpr
        sz = float(self.arrow_state.get("size", 60)) * dpr
        if x1 == x2 and y1 == y2:
            return None
        return (x1, y1, x2, y2, sz)

    def step_once(self) -> float:
        """Perform one vision capture/analyze tick; returns suggested sleep delay."""
        now = time.time()

        if not self.arrow_state.get("enabled", True):
            need_repaint = False
            with self._lock:
                self._active_board_key = ""
                self._last_req_sig = None
                need_repaint = self._clear_vision_arrow_locked("disabled")
            self.engine.stop_search()
            if need_repaint:
                self._emit_repaint()
            return 0.18

        if self._extension_is_fresh(now):
            need_repaint = False
            with self._lock:
                self._active_board_key = ""
                self._last_req_sig = None
                if self.arrow_state.get("vision_active", False):
                    self.arrow_state["vision_active"] = False
                    self.arrow_state["vision_status"] = "yielded"
                    need_repaint = True
            self.engine.stop_search()
            if need_repaint:
                self._emit_repaint()
            return 0.25

        if (now - self._last_browser_check_ts) >= 0.4 or self._last_browser_check_ts == 0.0:
            detected = self.browser_detect_fn()
            hwnd = int(detected.get("hwnd", 0) or 0) if detected else 0
            self._cached_browser = detected
            self._cached_dpr = max(0.5, float(self.dpr_fn(hwnd)))
            self._last_browser_check_ts = now
        else:
            detected = self._cached_browser

        if detected and detected.get("name"):
            self.arrow_state["detected_browser"] = detected["name"]

        dpr = self._cached_dpr
        arrow_px = self._current_arrow_px(dpr)

        b = self.detector.bounds
        res = None
        if b is not None:
            rx = max(0, b.x - 16)
            ry = max(0, b.y - 16)
            rw = (b.x + b.size + 16) - rx
            rh = (b.y + b.size + 16) - ry
            frame = self.capture_fn((rx, ry, rw, rh))
            if frame is not None:
                roi_offset = (rx, ry) if (frame.shape[1] == rw and frame.shape[0] == rh) else (0, 0)
                res = self.detector.process_frame(frame, arrow_px=arrow_px, roi_offset=roi_offset)
            if res is None or res.status == "no_board":
                frame_full = self.capture_fn(None)
                if frame_full is not None:
                    res = self.detector.process_frame(frame_full, arrow_px=arrow_px)
        else:
            frame = self.capture_fn(None)
            if frame is not None:
                res = self.detector.process_frame(frame, arrow_px=arrow_px)

        if res is None:
            return 0.15

        if res.status == "no_board":
            self._no_board_streak += 1
            if self._no_board_streak < 4 and self._active_board_key:
                return 0.12 if detected else 0.25
            need_repaint = False
            with self._lock:
                if self._active_board_key:
                    self.engine.stop_search()
                self._active_board_key = ""
                self._last_req_sig = None
                need_repaint = self._clear_vision_arrow_locked("waiting")
            if need_repaint:
                self._emit_repaint()
            return 0.18 if detected else 0.30

        self._no_board_streak = 0

        if res.status == "need_start_pos":
            need_repaint = False
            with self._lock:
                if self._active_board_key:
                    self.engine.stop_search()
                self._active_board_key = ""
                self._last_req_sig = None
                need_repaint = self._clear_vision_arrow_locked("need_start_pos")
                self.arrow_state["vision_active"] = True
                self.arrow_state["last_seen"] = time.time()
            if need_repaint:
                self._emit_repaint()
            return 0.10

        # res.status == "ok"
        assert res.bounds is not None and res.fen is not None
        skill = int(self.arrow_state.get("skill", 20) or 20)
        target_depth = int(self.arrow_state.get("target_depth", 12) or 12)
        side_pref = str(self.arrow_state.get("side", "auto") or "auto")
        req_sig = (res.board_key, skill, target_depth, side_pref)

        should_analyze = self._should_analyze_turn(res.turn, res.flipped)
        need_search = False
        need_repaint = False

        with self._lock:
            board_changed = res.board_key != self._active_board_key
            bounds_shifted = (
                self._active_bounds is None
                or abs(res.bounds.x - self._active_bounds.x) > 1
                or abs(res.bounds.y - self._active_bounds.y) > 1
                or abs(res.bounds.size - self._active_bounds.size) > 1
                or abs(dpr - self._active_dpr) > 0.02
            )

            self._active_bounds = res.bounds
            self._active_flipped = res.flipped
            self._active_dpr = dpr
            self._active_fen = res.fen
            self.arrow_state["last_seen"] = time.time()
            self.arrow_state["vision_active"] = True
            self.arrow_state["flipped"] = res.flipped

            if board_changed:
                # Immediately drop any stale arrow when a move is detected on board
                self._active_board_key = res.board_key
                self._last_drawn_arrow_px = None
                if self.arrow_state.get("show", False):
                    self.arrow_state["show"] = False
                    need_repaint = True

            if not should_analyze:
                if self._last_req_sig is not None:
                    self.engine.stop_search()
                self._last_req_sig = req_sig
                self.arrow_state["vision_status"] = "opponent_turn"
                if self.arrow_state.get("show", False):
                    self.arrow_state["show"] = False
                    need_repaint = True
            else:
                self.arrow_state["vision_status"] = "active"
                if req_sig != self._last_req_sig:
                    self._last_req_sig = req_sig
                    need_search = True
                elif self.arrow_state.get("show", False) and self.arrow_state.get("move"):
                    mv = str(self.arrow_state["move"])
                    origin_missing = False
                    try:
                        fsq = parse_sq(mv[:2])
                        cur_piece = str(self.arrow_state.get("piece") or "")
                        cur_side = (piece_side(cur_piece) if cur_piece else res.turn) or None
                        if self.detector.is_square_occupied_by(fsq, cur_side) is False:
                            origin_missing = True
                    except ValueError:
                        origin_missing = True
                    if origin_missing:
                        self.arrow_state["show"] = False
                        self._last_drawn_arrow_px = None
                        self._last_req_sig = None
                        self._active_board_key = ""
                        need_repaint = True
                    elif bounds_shifted:
                        # Keep existing move arrow aligned immediately if browser window moved
                        try:
                            fr, fc = sq_to_screen_rc(parse_sq(mv[:2]), flipped=res.flipped)
                            tr, tc = sq_to_screen_rc(parse_sq(mv[2:4]), flipped=res.flipped)
                            sq_px = res.bounds.size / 8.0
                            fx_px = res.bounds.x + (fc + 0.5) * sq_px
                            fy_px = res.bounds.y + (fr + 0.5) * sq_px
                            tx_px = res.bounds.x + (tc + 0.5) * sq_px
                            ty_px = res.bounds.y + (tr + 0.5) * sq_px
                            self._last_drawn_arrow_px = (fx_px, fy_px, tx_px, ty_px, sq_px)
                            self.arrow_state["x1"] = int(round(fx_px / dpr))
                            self.arrow_state["y1"] = int(round(fy_px / dpr))
                            self.arrow_state["x2"] = int(round(tx_px / dpr))
                            self.arrow_state["y2"] = int(round(ty_px / dpr))
                            self.arrow_state["size"] = max(16, int(round(sq_px / dpr)))
                            need_repaint = True
                        except ValueError:
                            pass

        if need_repaint:
            self._emit_repaint()
        if need_search:
            self.engine.analyze(
                res.fen,
                depth=target_depth,
                board_key=res.board_key,
                skill=skill,
                on_update=self._on_engine_update,
            )

        return self.poll_interval_s

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="ChessVisionRunner", daemon=True)
        self._thread.start()

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            delay = self.poll_interval_s
            try:
                delay = self.step_once()
            except Exception:
                delay = 0.20
            self._stop_event.wait(delay)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None
        if self.owns_engine:
            self.engine.shutdown()
        else:
            self.engine.stop_search()
