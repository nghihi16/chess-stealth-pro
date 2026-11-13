import os
import sys
import time
import cv2
import numpy as np
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from vision_core.board_detector import (
    BoardBounds,
    BoardDetector,
    locate_board_bgr,
)
from vision_core.chess_rules import START_FEN, ChessBoardState, sq_to_screen_rc


ARTIFACT_DIR = r"C:\Users\Windows\.gemini\antigravity-cli\brain\cc3b4c1b-8ad3-4a28-9821-be072a60b176"
CHROME_START_PNG = os.path.join(ARTIFACT_DIR, "chrome_live_after_fix.png")
BRAVE_MOVE2_PNG = os.path.join(ARTIFACT_DIR, "brave_live_after_fix.png")
DESKTOP_NOBOARD_PNG = os.path.join(ARTIFACT_DIR, "screen_before_setup.png")


def _draw_synthetic_piece(img: np.ndarray, x0: int, y0: int, sq: int, ch: str) -> None:
    cx, cy = x0 + sq // 2, y0 + sq // 2
    is_white = ch.isupper()
    fill = (240, 240, 232) if is_white else (34, 34, 42)
    edge = (30, 30, 30) if is_white else (210, 210, 220)
    kind = ch.lower()
    r = max(6, sq // 4)
    if kind == "p":
        cv2.circle(img, (cx, cy - r // 3), int(r * 0.6), fill, -1)
        cv2.circle(img, (cx, cy - r // 3), int(r * 0.6), edge, 2)
        cv2.rectangle(img, (cx - r // 2, cy + 2), (cx + r // 2, cy + r), fill, -1)
    elif kind == "r":
        cv2.rectangle(img, (cx - int(r * 0.7), cy - int(r * 0.7)), (cx + int(r * 0.7), cy + r), fill, -1)
        cv2.rectangle(img, (cx - int(r * 0.7), cy - int(r * 0.7)), (cx + int(r * 0.7), cy + r), edge, 2)
    elif kind == "n":
        pts = np.array([[cx - r // 2, cy + r], [cx - r // 2, cy - r // 2], [cx + r // 2, cy - r // 4], [cx + r // 3, cy + r]])
        cv2.fillPoly(img, [pts], fill)
        cv2.polylines(img, [pts], True, edge, 2)
    elif kind == "b":
        cv2.ellipse(img, (cx, cy), (int(r * 0.55), r), 0, 0, 360, fill, -1)
        cv2.ellipse(img, (cx, cy), (int(r * 0.55), r), 0, 0, 360, edge, 2)
    elif kind == "q":
        pts = np.array([[cx - r, cy - r // 2], [cx, cy - r], [cx + r, cy - r // 2], [cx + int(r * 0.7), cy + r], [cx - int(r * 0.7), cy + r]])
        cv2.fillPoly(img, [pts], fill)
        cv2.polylines(img, [pts], True, edge, 2)
    elif kind == "k":
        cv2.rectangle(img, (cx - int(r * 0.8), cy - int(r * 0.4)), (cx + int(r * 0.8), cy + r), fill, -1)
        cv2.line(img, (cx, cy - r), (cx, cy - r // 3), edge, 3)
        cv2.line(img, (cx - r // 3, cy - int(r * 0.7)), (cx + r // 3, cy - int(r * 0.7)), edge, 3)


def _render_synthetic_frame(
    state: ChessBoardState,
    *,
    width: int = 1280,
    height: int = 800,
    bx: int = 240,
    by: int = 100,
    sq: int = 75,
    flipped: bool = False,
    light_bgr=(210, 238, 238),
    dark_bgr=(86, 150, 118),
    highlights: tuple[int, int] | None = None,
    skip_pieces_on: set[int] | None = None,
    arrow: tuple[tuple[int, int], tuple[int, int]] | None = None,
) -> np.ndarray:
    img = np.full((height, width, 3), (38, 32, 30), dtype=np.uint8)
    grid = state.to_grid(flipped=flipped)
    hl_set = set(highlights or ())
    skip_set = skip_pieces_on or set()
    for r in range(8):
        for c in range(8):
            x0, y0 = bx + c * sq, by + r * sq
            base = light_bgr if (r + c) % 2 == 0 else dark_bgr
            from vision_core.chess_rules import screen_rc_to_sq

            sq_idx = screen_rc_to_sq(r, c, flipped=flipped)
            if sq_idx in hl_set:
                base = (int(base[0] * 0.5 + 30), int(min(255, base[1] * 0.7 + 75)), int(min(255, base[2] * 0.7 + 75)))
            img[y0 : y0 + sq, x0 : x0 + sq] = base
            piece = grid[r][c]
            if piece and sq_idx not in skip_set:
                _draw_synthetic_piece(img, x0, y0, sq, piece)
    if arrow is not None:
        p1, p2 = arrow
        cv2.arrowedLine(img, p1, p2, (20, 165, 255), thickness=max(10, sq // 6), tipLength=0.25)
    return img


@pytest.mark.skipif(not os.path.isfile(CHROME_START_PNG), reason="Real Chrome screenshot artifact missing")
def test_locate_board_real_chrome_and_brave_screenshots():
    chrome_img = cv2.imread(CHROME_START_PNG)
    assert chrome_img is not None
    # Warm up OpenCV buffers once before timing
    _ = locate_board_bgr(chrome_img)
    t0 = time.perf_counter()
    c_bounds = locate_board_bgr(chrome_img)
    dt_ms = (time.perf_counter() - t0) * 1000.0

    assert c_bounds is not None
    assert abs(c_bounds.x - 280) <= 3
    assert abs(c_bounds.y - 232) <= 3
    assert abs(c_bounds.size - 712) <= 4
    assert dt_ms < 60.0, f"Board locator too slow: {dt_ms:.1f} ms"

    if os.path.isfile(BRAVE_MOVE2_PNG):
        brave_img = cv2.imread(BRAVE_MOVE2_PNG)
        b_bounds = locate_board_bgr(brave_img)
        assert b_bounds is not None
        assert abs(b_bounds.x - 377) <= 3
        assert abs(b_bounds.y - 183) <= 3
        assert abs(b_bounds.size - 760) <= 4


def test_detect_non_chess_screen_returns_none():
    blank = np.full((900, 1600, 3), (45, 45, 52), dtype=np.uint8)
    cv2.rectangle(blank, (100, 80), (1400, 820), (65, 65, 75), 3)
    assert locate_board_bgr(blank) is None

    if os.path.isfile(DESKTOP_NOBOARD_PNG):
        desk = cv2.imread(DESKTOP_NOBOARD_PNG)
        assert locate_board_bgr(desk) is None


@pytest.mark.skipif(
    not (os.path.isfile(CHROME_START_PNG) and os.path.isfile(BRAVE_MOVE2_PNG)),
    reason="Real screenshot fixtures missing",
)
def test_custom_theme_start_calibration_and_2ply_recovery_with_arrow_mask():
    chrome_img = cv2.imread(CHROME_START_PNG)
    brave_img = cv2.imread(BRAVE_MOVE2_PNG)

    detector = BoardDetector()
    res1 = detector.process_frame(chrome_img)
    assert res1.status == "ok"
    assert res1.flipped is False
    assert res1.fen == START_FEN

    # Brave fixture shows Grand Chess Auto at 760x760 (x=377, y=183) after 1. e4 h5
    # with an orange overlay arrow drawn from b1 (col 1, row 7) to c3 (col 2, row 5).
    sq = 760.0 / 8.0
    arrow_px = (
        377 + 1.5 * sq,
        183 + 7.5 * sq,
        377 + 2.5 * sq,
        183 + 5.5 * sq,
        sq,
    )
    res2 = detector.process_frame(brave_img, arrow_px=arrow_px)
    assert res2.status == "ok"
    assert res2.fen == "rnbqkbnr/ppppppp1/8/7p/4P3/8/PPPP1PPP/RNBQKBNR w KQkq h6 0 2"


def test_simulated_game_sequence_with_arrow_mask_and_early_highlight():
    detector = BoardDetector()
    state = ChessBoardState.starting_position()

    # 1. Start frame (white bottom)
    img0 = _render_synthetic_frame(state)
    r0 = detector.process_frame(img0)
    assert r0.status == "ok"
    assert r0.fen == START_FEN

    # 2. Early highlight before piece bitmap updates on 1. e4
    e2_sq, e4_sq = 12, 28
    img_hl = _render_synthetic_frame(state, highlights=(e2_sq, e4_sq))
    r_hl = detector.process_frame(img_hl)
    assert r_hl.status == "ok"
    assert r_hl.last_move == "e2e4"
    assert r_hl.fen == state.push_uci("e2e4").to_fen()

    # 3. Full settled frame after e2e4 -> e7e5 -> Nf3 (with arrow drawn on screen)
    state = state.push_uci("e2e4")
    img_settled = _render_synthetic_frame(state, highlights=(e2_sq, e4_sq))
    r_same = detector.process_frame(img_settled)
    assert r_same.status == "ok"
    assert r_same.fen == state.to_fen()

    for mv in ("e7e5", "g1f3", "b8c6", "f1c4", "g8f6", "e1g1"):
        state = state.push_uci(mv)
        arrow_px = (240 + 3.5 * 75, 100 + 6.5 * 75, 240 + 3.5 * 75, 100 + 4.5 * 75, 75)
        frame = _render_synthetic_frame(
            state,
            arrow=((int(arrow_px[0]), int(arrow_px[1])), (int(arrow_px[2]), int(arrow_px[3]))),
        )
        res = detector.process_frame(frame, arrow_px=arrow_px)
        assert res.status == "ok", f"Failed after {mv}: {res}"
        assert res.fen == state.to_fen(), f"FEN mismatch after {mv}: {res.fen} vs {state.to_fen()}"


def test_flipped_board_auto_correction_on_move_1():
    # Intentionally render a board flipped=True where luminance alone matches/tricks heuristics,
    # then White plays 1. d2d4 from the TOP side (rows 0/1 -> row 3).
    state = ChessBoardState.starting_position()
    img0 = _render_synthetic_frame(state, flipped=True, light_bgr=(220, 220, 220), dark_bgr=(100, 120, 150))
    # Even if inverted piece colors tricked side guess, Move 1 reveals which side is White:
    detector = BoardDetector()
    r0 = detector.process_frame(img0)
    assert r0.status == "ok"
    assert r0.fen == START_FEN

    state1 = state.push_uci("d2d4")
    img1 = _render_synthetic_frame(state1, flipped=True, light_bgr=(220, 220, 220), dark_bgr=(100, 120, 150))
    r1 = detector.process_frame(img1)
    assert r1.status == "ok"
    assert r1.flipped is True
    assert r1.fen == state1.to_fen()


def test_unrecognized_custom_midgame_reports_need_start_pos():
    mid_state = ChessBoardState.from_fen("r2q1rk1/ppp2ppp/2n1bn2/3p4/3P4/2N1PN2/PPP2PPP/R2QKB1R w KQ - 4 7")
    img = _render_synthetic_frame(mid_state)
    detector = BoardDetector()
    res = detector.process_frame(img)
    assert res.status == "need_start_pos"
    assert res.bounds is not None
    assert res.fen is None


def test_capture_screen_bgr_handles_64bit_gdi_handles():
    import ctypes
    from ctypes import wintypes
    import vision_core.board_detector as bd

    user32, gdi32 = bd._win32_gdi()
    assert gdi32.GetDIBits.argtypes[-3] is ctypes.c_void_p
    assert gdi32.CreateCompatibleDC.restype is wintypes.HDC
    assert gdi32.DeleteDC.argtypes == [wintypes.HDC]

    class _FakeUser32:
        def GetDC(self, _hwnd):
            return 0xFFFFFFFF12340001

        def ReleaseDC(self, _hwnd, hdc):
            calls.append(("ReleaseDC", hdc))
            return 1

    class _FakeGdi32:
        def CreateCompatibleDC(self, _hdc):
            return 0xFFFFFFFFD607367E

        def CreateCompatibleBitmap(self, _hdc, _w, _h):
            return 0xFFFFFFFFCAFEBABE

        def SelectObject(self, hdc, obj):
            calls.append(("SelectObject", hdc, obj))
            return 0xFFFFFFFF00001234

        def BitBlt(self, *_args):
            return 1

        def GetDIBits(self, _hdc, _hbmp, _start, rows, ptr, _bmi, _usage):
            assert isinstance(ptr, ctypes.c_void_p)
            return rows

        def DeleteObject(self, obj):
            calls.append(("DeleteObject", obj))
            return 1

        def DeleteDC(self, hdc):
            calls.append(("DeleteDC", hdc))
            return 1

    calls = []
    old_cache = bd._WIN32_GDI_CACHE
    bd._WIN32_GDI_CACHE = (_FakeUser32(), _FakeGdi32())
    try:
        frame = bd.capture_screen_bgr(roi=(10, 20, 32, 24))
    finally:
        bd._WIN32_GDI_CACHE = old_cache

    assert frame is not None and frame.shape == (24, 32, 3)
    assert ("DeleteDC", 0xFFFFFFFFD607367E) in calls
    assert ("DeleteObject", 0xFFFFFFFFCAFEBABE) in calls
    assert ("ReleaseDC", 0xFFFFFFFF12340001) in calls


def test_midslide_e2e3_does_not_corrupt_e2e4_and_slip_recovers_turn():
    # 1. Start position followed by a transient mid-slide frame where the pawn is passing e3
    #    while highlights on (e2, e4) already indicate e2e4 (must reject e2e3).
    detector = BoardDetector()
    start = ChessBoardState.starting_position()
    r0 = detector.process_frame(_render_synthetic_frame(start))
    assert r0.status == "ok" and r0.fen == START_FEN

    e2_sq, e4_sq = 12, 28
    mid_slide = start.push_uci("e2e3")
    r_slide = detector.process_frame(_render_synthetic_frame(mid_slide, highlights=(e2_sq, e4_sq)))
    assert r_slide.status == "ok"
    assert r_slide.last_move == ""
    assert r_slide.turn == "w"

    settled_e4 = start.push_uci("e2e4")
    r_e4 = detector.process_frame(_render_synthetic_frame(settled_e4, highlights=(e2_sq, e4_sq)))
    assert r_e4.status == "ok"
    assert r_e4.turn == "b"
    assert r_e4.fen == settled_e4.to_fen()

    # 2. Even if an unhighlighted slip falsely committed e2e3, 1. e4 g5 (g7, g5 highlighted)
    #    must recover via _prev_state to White's turn instead of resyncing backwards to e3e4.
    d2 = BoardDetector()
    d2.process_frame(_render_synthetic_frame(start))
    d2._prev_state = start
    d2.state = start.push_uci("e2e3")
    g7_sq, g5_sq = 54, 38
    after_g5 = settled_e4.push_uci("g7g5")
    r_rec = d2.process_frame(_render_synthetic_frame(after_g5, highlights=(g7_sq, g5_sq)))
    assert r_rec.status == "ok"
    assert r_rec.turn == "w"
    assert r_rec.last_move == "g7g5"
    assert r_rec.fen == after_g5.to_fen()
