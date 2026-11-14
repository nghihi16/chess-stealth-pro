import os
import sys
import time
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tests.test_board_detector import _render_synthetic_frame
from vision_core.chess_rules import ChessBoardState
from vision_core.vision_runner import VisionRunner


class _StubEngine:
    def __init__(self, move_by_fen=None):
        self.calls = []
        self.stopped = 0
        self.shutdown_calls = 0
        self.move_by_fen = move_by_fen or {}

    def analyze(self, fen, depth, board_key, skill=20, on_update=None):
        self.calls.append((fen, depth, board_key, skill))
        mv = self.move_by_fen.get(fen, "g1f3")
        if on_update:
            on_update({
                "board_key": board_key,
                "fen": fen,
                "move": mv,
                "ponder": "b8c6",
                "depth": str(depth),
                "eval": "+0.3",
                "final": True,
            })
        return len(self.calls)

    def stop_search(self):
        self.stopped += 1

    def shutdown(self):
        self.shutdown_calls += 1


def _fresh_arrow_state():
    return {
        "x1": 0,
        "y1": 0,
        "x2": 0,
        "y2": 0,
        "size": 60,
        "show": False,
        "enabled": True,
        "side": "auto",
        "skill": 20,
        "target_depth": 12,
        "move": "",
        "depth": "",
        "eval": "+0.0",
        "ponder": "",
        "piece": "",
        "last_seen": 0.0,
        "last_ping": 0.0,
        "offset_y": 0,
        "auto_aligned": False,
        "detected_browser": "",
    }


def test_vision_runner_analyzes_detected_board_and_maps_physical_to_qt_coords():
    state = ChessBoardState.starting_position()
    frame = _render_synthetic_frame(state, bx=240, by=100, sq=75)
    arrow_state = _fresh_arrow_state()
    engine = _StubEngine({state.to_fen(): "e2e4"})
    repaints = {"n": 0}

    runner = VisionRunner(
        arrow_state=arrow_state,
        engine=engine,
        capture_fn=lambda _roi=None: frame,
        browser_detect_fn=lambda: {"name": "Google Chrome", "key": "chrome", "hwnd": 111},
        dpr_fn=lambda _hwnd: 1.25,
        on_repaint=lambda: repaints.__setitem__("n", repaints["n"] + 1),
    )

    runner.step_once()

    assert len(engine.calls) == 1
    assert arrow_state["show"] is True
    assert arrow_state["move"] == "e2e4"
    assert arrow_state["piece"] == "P"
    assert arrow_state["auto_aligned"] is True
    assert arrow_state["vision_active"] is True
    assert repaints["n"] >= 1

    # Physical center of e2 (row 6, col 4) and e4 (row 4, col 4) divided by 1.25 DPR
    bounds = runner.detector.bounds
    sq_px = bounds.size / 8.0
    exp_x1 = (bounds.x + 4.5 * sq_px) / 1.25
    exp_y1 = (bounds.y + 6.5 * sq_px) / 1.25
    exp_x2 = (bounds.x + 4.5 * sq_px) / 1.25
    exp_y2 = (bounds.y + 4.5 * sq_px) / 1.25
    assert abs(arrow_state["x1"] - exp_x1) <= 1.2
    assert abs(arrow_state["y1"] - exp_y1) <= 1.2
    assert abs(arrow_state["x2"] - exp_x2) <= 1.2
    assert abs(arrow_state["y2"] - exp_y2) <= 1.2
    assert abs(arrow_state["size"] - round(sq_px / 1.25)) <= 1


def test_vision_runner_clears_stale_arrow_on_move_and_reanalyzes():
    s0 = ChessBoardState.starting_position()
    s1 = s0.push_uci("e2e4")
    s2 = s1.push_uci("e7e5")
    frames = [
        _render_synthetic_frame(s0),
        _render_synthetic_frame(s1),
        _render_synthetic_frame(s2),
    ]
    idx = {"i": 0}
    arrow_state = _fresh_arrow_state()
    engine = _StubEngine({s0.to_fen(): "e2e4", s2.to_fen(): "g1f3"})

    runner = VisionRunner(
        arrow_state=arrow_state,
        engine=engine,
        capture_fn=lambda _roi=None: frames[idx["i"]],
        browser_detect_fn=lambda: {"name": "Google Chrome", "key": "chrome", "hwnd": 1},
        dpr_fn=lambda _hwnd: 1.0,
    )

    runner.step_once()
    assert arrow_state["show"] is True
    assert arrow_state["move"] == "e2e4"

    # After 1. e4 it is Black's turn while flipped=False (White player): clear stale arrow immediately
    idx["i"] = 1
    runner.step_once()
    assert arrow_state["show"] is False

    # After 1... e5 it is White's turn again: new Stockfish arrow must appear
    idx["i"] = 2
    runner.step_once()
    assert arrow_state["show"] is True
    assert arrow_state["move"] == "g1f3"
    assert len(engine.calls) == 2


def test_vision_runner_yields_when_extension_ping_is_fresh():
    s0 = ChessBoardState.starting_position()
    frame = _render_synthetic_frame(s0)
    arrow_state = _fresh_arrow_state()
    arrow_state["last_ping"] = time.time()
    arrow_state["show"] = True
    arrow_state["move"] = "d2d4"

    engine = _StubEngine({s0.to_fen(): "e2e4"})
    runner = VisionRunner(
        arrow_state=arrow_state,
        engine=engine,
        capture_fn=lambda _roi=None: frame,
        browser_detect_fn=lambda: {"name": "Brave", "key": "brave", "hwnd": 1},
    )

    runner.step_once()
    assert engine.calls == []
    assert arrow_state["move"] == "d2d4"
    assert arrow_state.get("vision_active", False) is False


def test_vision_runner_respects_deactivate_and_clears_arrow():
    s0 = ChessBoardState.starting_position()
    frame = _render_synthetic_frame(s0)
    arrow_state = _fresh_arrow_state()
    engine = _StubEngine({s0.to_fen(): "e2e4"})
    runner = VisionRunner(
        arrow_state=arrow_state,
        engine=engine,
        capture_fn=lambda _roi=None: frame,
        browser_detect_fn=lambda: {"name": "Google Chrome", "key": "chrome", "hwnd": 1},
    )

    runner.step_once()
    assert arrow_state["show"] is True

    arrow_state["enabled"] = False
    runner.step_once()
    assert arrow_state["show"] is False
    assert arrow_state.get("vision_active", False) is False
    assert engine.stopped >= 1


def test_vision_runner_debounces_transient_no_board():
    import numpy as np

    s0 = ChessBoardState.starting_position()
    board_frame = _render_synthetic_frame(s0)
    blank_frame = np.full((800, 1280, 3), (30, 30, 35), dtype=np.uint8)
    frames = {"cur": board_frame}
    arrow_state = _fresh_arrow_state()
    engine = _StubEngine({s0.to_fen(): "e2e4"})

    runner = VisionRunner(
        arrow_state=arrow_state,
        engine=engine,
        capture_fn=lambda _roi=None: frames["cur"],
        browser_detect_fn=lambda: {"name": "Google Chrome", "key": "chrome", "hwnd": 1},
    )
    runner.step_once()
    assert arrow_state["show"] is True
    assert arrow_state["move"] == "e2e4"

    # Transient 1-3 missing frames must keep arrow rock-solid (no flicker)
    frames["cur"] = blank_frame
    for _ in range(3):
        runner.step_once()
        assert arrow_state["show"] is True
        assert arrow_state["move"] == "e2e4"

    # 4th consecutive no_board frame clears the arrow
    runner.step_once()
    assert arrow_state["show"] is False


def test_vision_runner_refuses_arrow_on_empty_origin_square():
    s0 = ChessBoardState.starting_position()
    frame = _render_synthetic_frame(s0)
    arrow_state = _fresh_arrow_state()
    # Intentionally bogus engine output whose from_sq 'e4' is EMPTY on s0
    engine = _StubEngine({s0.to_fen(): "e4e5"})

    runner = VisionRunner(
        arrow_state=arrow_state,
        engine=engine,
        capture_fn=lambda _roi=None: frame,
        browser_detect_fn=lambda: {"name": "Google Chrome", "key": "chrome", "hwnd": 1},
    )
    runner.step_once()
    assert arrow_state["show"] is False


def test_vision_runner_uses_roi_capture_after_lock():
    s0 = ChessBoardState.starting_position()
    full_frame = _render_synthetic_frame(s0, width=1440, height=900, bx=300, by=120, sq=75)
    seen_rois = []

    def _cap(roi=None):
        seen_rois.append(roi)
        if roi is None:
            return full_frame
        x, y, w, h = roi
        return full_frame[y : y + h, x : x + w]

    arrow_state = _fresh_arrow_state()
    engine = _StubEngine({s0.to_fen(): "e2e4"})
    runner = VisionRunner(
        arrow_state=arrow_state,
        engine=engine,
        capture_fn=_cap,
        browser_detect_fn=lambda: {"name": "Google Chrome", "key": "chrome", "hwnd": 1},
    )
    runner.step_once()
    assert seen_rois == [None]
    assert arrow_state["show"] is True

    seen_rois.clear()
    runner.step_once()
    assert len(seen_rois) == 1
    assert seen_rois[0] is not None
    assert arrow_state["show"] is True
    assert arrow_state["move"] == "e2e4"


def test_vision_runner_ignores_non_final_intermediate_engine_updates():
    s0 = ChessBoardState.starting_position()
    frame = _render_synthetic_frame(s0)

    class _PartialThenFinalEngine:
        def __init__(self, emit_final: bool):
            self.emit_final = emit_final
            self.stopped = 0

        def analyze(self, fen, depth, board_key, skill=20, on_update=None):
            if on_update:
                on_update({
                    "board_key": board_key,
                    "fen": fen,
                    "move": "d2d4",
                    "depth": "1",
                    "eval": "+0.1",
                    "final": False,
                })
                if self.emit_final:
                    on_update({
                        "board_key": board_key,
                        "fen": fen,
                        "move": "e2e4",
                        "depth": "12",
                        "eval": "+0.4",
                        "final": True,
                    })
            return 1

        def stop_search(self):
            self.stopped += 1

        def shutdown(self):
            pass

    arrow_partial_only = _fresh_arrow_state()
    runner_partial = VisionRunner(
        arrow_state=arrow_partial_only,
        engine=_PartialThenFinalEngine(emit_final=False),
        capture_fn=lambda _roi=None: frame,
        browser_detect_fn=lambda: {"name": "Google Chrome", "key": "chrome", "hwnd": 1},
    )
    runner_partial.step_once()
    assert arrow_partial_only["show"] is False

    arrow_final = _fresh_arrow_state()
    runner_final = VisionRunner(
        arrow_state=arrow_final,
        engine=_PartialThenFinalEngine(emit_final=True),
        capture_fn=lambda _roi=None: frame,
        browser_detect_fn=lambda: {"name": "Google Chrome", "key": "chrome", "hwnd": 1},
    )
    runner_final.step_once()
    assert arrow_final["show"] is True
    assert arrow_final["move"] == "e2e4"

