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
from vision_core.chess_rules import START_FEN, ChessBoardState, screen_rc_to_sq, sq_to_screen_rc


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


def _draw_qt_arrow(img: np.ndarray, bx: int, by: int, sq: float, mv: str, flipped: bool = False) -> tuple[float, float, float, float, float]:
    """Render QtStealthOverlay's exact 7-point orange arrow polygon onto synthetic image."""
    from vision_core.chess_rules import parse_sq

    fr, fc = sq_to_screen_rc(parse_sq(mv[:2]), flipped=flipped)
    tr, tc = sq_to_screen_rc(parse_sq(mv[2:4]), flipped=flipped)
    x1, y1 = bx + (fc + 0.5) * sq, by + (fr + 0.5) * sq
    x2, y2 = bx + (tc + 0.5) * sq, by + (tr + 0.5) * sq
    dx, dy = x2 - x1, y2 - y1
    dist = float(np.hypot(dx, dy))
    ux, uy = dx / dist, dy / dist
    px, py = -uy, ux
    shaft_w = sq * 0.22
    head_w = sq * 0.50
    head_l = sq * 0.38
    offset = sq * 0.12
    sx, sy = x1 + ux * offset, y1 + uy * offset
    nx, ny = x2 - ux * head_l, y2 - uy * head_l
    poly = np.array(
        [
            [sx + px * (shaft_w / 2), sy + py * (shaft_w / 2)],
            [nx + px * (shaft_w / 2), ny + py * (shaft_w / 2)],
            [nx + px * (head_w / 2), ny + py * (head_w / 2)],
            [x2, y2],
            [nx - px * (head_w / 2), ny - py * (head_w / 2)],
            [nx - px * (shaft_w / 2), ny - py * (shaft_w / 2)],
            [sx - px * (shaft_w / 2), sy - py * (shaft_w / 2)],
        ],
        dtype=np.float32,
    )
    cv2.fillPoly(img, [np.rint(poly).astype(np.int32)], (11, 158, 245))
    cv2.polylines(img, [np.rint(poly).astype(np.int32)], True, (0, 0, 0), 2)
    return (x1, y1, x2, y2, sq)


def test_simulated_game_sequence_with_arrow_mask_and_early_highlight():
    detector = BoardDetector()
    state = ChessBoardState.starting_position()

    # 1. Start frame (white bottom)
    img0 = _render_synthetic_frame(state)
    r0 = detector.process_frame(img0)
    assert r0.status == "ok"
    assert r0.fen == START_FEN

    # 2. Highlights alone before pieces move must NOT prematurely advance state,
    #    and a wide Qt orange arrow over the suggested move must NOT fabricate a phantom move!
    e2_sq, e4_sq = 12, 28
    img_hl = _render_synthetic_frame(state, highlights=(e2_sq, e4_sq))
    arrow_e2e4 = _draw_qt_arrow(img_hl, 240, 100, 75.0, "e2e4")
    r_hl = detector.process_frame(img_hl, arrow_px=arrow_e2e4)
    assert r_hl.status == "ok"
    assert r_hl.fen == START_FEN
    assert r_hl.last_move == ""

    # 3. Play 8 moves while drawing Qt-geometry arrows directly over candidate moves
    moves = ("e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "g8f6", "e1g1", "f8c5")
    for idx, mv in enumerate(moves):
        # Verify an arrow drawn on the current position BEFORE the move NEVER fabricates a phantom move
        pre_frame = _render_synthetic_frame(state)
        pre_arrow = _draw_qt_arrow(pre_frame, 240, 100, 75.0, mv)
        r_pre = detector.process_frame(pre_frame, arrow_px=pre_arrow)
        assert r_pre.fen == state.to_fen(), f"Arrow caused phantom transition before {mv}: {r_pre.fen}"

        # Now apply the move while arrow is still overlaid on from_sq -> to_sq
        state = state.push_uci(mv)
        frame = _render_synthetic_frame(state)
        post_arrow = _draw_qt_arrow(frame, 240, 100, 75.0, mv)
        res = detector.process_frame(frame, arrow_px=post_arrow)
        assert res.status == "ok", f"Failed after {mv} (#{idx}): {res}"
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


def test_mid_slide_intermediate_square_revises_to_final_square():
    detector = BoardDetector()
    s0 = ChessBoardState.starting_position()
    assert detector.process_frame(_render_synthetic_frame(s0)).status == "ok"

    # Slide 1: e2 passes e3 without highlights -> settled on e4 must revise e2e3 -> e2e4
    s_e3 = s0.push_uci("e2e3")
    detector.process_frame(_render_synthetic_frame(s_e3))
    s_e4 = s0.push_uci("e2e4")
    r_e4 = detector.process_frame(_render_synthetic_frame(s_e4))
    assert r_e4.fen == s_e4.to_fen()

    # After 1... e5, White plays f1c4 passing intermediate squares e2 and d3 along the diagonal
    s_e5 = s_e4.push_uci("e7e5")
    assert detector.process_frame(_render_synthetic_frame(s_e5)).fen == s_e5.to_fen()
    for mid_mv in ("f1e2", "f1d3"):
        detector.process_frame(_render_synthetic_frame(s_e5.push_uci(mid_mv)))
    s_c4 = s_e5.push_uci("f1c4")
    r_c4 = detector.process_frame(_render_synthetic_frame(s_c4))
    assert r_c4.fen == s_c4.to_fen()


def test_template_self_healing_resync_after_multi_move_jump():
    detector = BoardDetector()
    state = ChessBoardState.starting_position()
    assert detector.process_frame(_render_synthetic_frame(state)).status == "ok"

    # Jump ahead by 5 plies (too far for 1-ply/2-ply tracking) without intermediate frames
    for mv in ("e2e4", "e7e5", "g1f3", "b8c6", "f1c4"):
        state = state.push_uci(mv)

    from vision_core.chess_rules import parse_sq

    jumped = _render_synthetic_frame(state, highlights=(parse_sq("f1"), parse_sq("c4")))
    detector.process_frame(jumped)
    res = detector.process_frame(jumped)
    assert res.status == "ok"
    assert res.source == "resync"
    assert res.fen is not None
    assert res.fen.split(" ")[:2] == state.to_fen().split(" ")[:2]


def test_queen_vs_knight_disambiguation_and_swap_self_repair():
    from dataclasses import replace
    from vision_core.chess_rules import parse_sq

    bx, by, sq = 240, 100, 75

    def _play_setup() -> tuple[BoardDetector, ChessBoardState]:
        det = BoardDetector()
        s = ChessBoardState.starting_position()
        assert det.process_frame(_render_synthetic_frame(s)).status == "ok"
        for mv in ("d2d4", "e7e5", "d4e5", "b8c6", "g1f3", "d7d6", "d1d3", "c6d4"):
            s = s.push_uci(mv)
            res_step = det.process_frame(_render_synthetic_frame(s, highlights=(parse_sq(mv[:2]), parse_sq(mv[2:4]))))
            assert res_step.status == "ok"
        assert det.state is not None and det.state.to_fen() == s.to_fen()
        return det, s

    # (a) Both Qd3xd4 (d3d4) and Nf3xd4 (f3d4) are legal captures onto d4 while a Qt arrow b3->g3
    #     crosses rank 3 over both d3 and f3. Detector must never confuse Q capture with N capture.
    det_q, s_base = _play_setup()
    s_qd4 = s_base.push_uci("d3d4")
    fr_q = _render_synthetic_frame(s_qd4)
    apx_q = _draw_qt_arrow(fr_q, bx, by, float(sq), "b3g3")
    res_q = det_q.process_frame(fr_q, arrow_px=apx_q)
    assert res_q.last_move == "d3d4"
    assert det_q.state is not None
    assert det_q.state.board[parse_sq("d4")] == "Q"
    assert det_q.state.board[parse_sq("f3")] == "N"

    det_n, s_base_n = _play_setup()
    s_nd4 = s_base_n.push_uci("f3d4")
    fr_n = _render_synthetic_frame(s_nd4)
    apx_n = _draw_qt_arrow(fr_n, bx, by, float(sq), "b3g3")
    res_n = det_n.process_frame(fr_n, arrow_px=apx_n)
    assert res_n.last_move == "f3d4"
    assert det_n.state is not None
    assert det_n.state.board[parse_sq("d4")] == "N"
    assert det_n.state.board[parse_sq("d3")] == "Q"

    # (b) Artificially swap Q and N in state while true board has Q on d4 and N on f3:
    #     verify_piece_at detects mismatch on last_obs, and steady-state self-repair swaps them back.
    det_rep, _ = _play_setup()
    assert det_rep.process_frame(_render_synthetic_frame(s_qd4)).last_move == "d3d4"
    assert det_rep.verify_piece_at("d4", "Q") is True
    assert det_rep.verify_piece_at("d4", "N") is False

    corrupted = list(s_qd4.board)
    corrupted[parse_sq("d4")] = "N"
    corrupted[parse_sq("f3")] = "Q"
    det_rep.state = replace(s_qd4, board=tuple(corrupted))
    det_rep._prev_fast_thumb = None
    repaired_res = det_rep.process_frame(_render_synthetic_frame(s_qd4))
    assert repaired_res.status == "ok"
    assert repaired_res.source == "resync"
    assert det_rep.state.board[parse_sq("d4")] == "Q"
    assert det_rep.state.board[parse_sq("f3")] == "N"

    # (c) Reconstructed board respects inventory limits (<= 1 Q, <= 2 N)
    det_rec, _ = _play_setup()
    obs_clean = det_rec.last_obs
    obs_by_sq = {screen_rc_to_sq(o.row, o.col, flipped=det_rec.flipped): o for o in obs_clean}
    expected_sides = {sq_i: det_rec._classify_side(o) for sq_i, o in obs_by_sq.items()}
    rec = det_rec._reconstruct_state_from_templates(obs_by_sq, expected_sides, None)
    assert rec is not None
    assert rec.board.count("Q") <= 1
    assert rec.board.count("N") <= 2




def test_opening_auto_calibration_joining_as_black_after_1e4():
    import time
    s1 = ChessBoardState.starting_position().push_uci("e2e4")
    img1 = _render_synthetic_frame(s1, flipped=True)
    det = BoardDetector()
    res = det.process_frame(img1, side_pref="auto")
    assert res.status == "ok"
    assert res.flipped is True
    assert res.turn == "b"
    assert res.fen == s1.to_fen()


def test_explicit_side_pref_locks_white_or_black_orientation():
    s0 = ChessBoardState.starting_position()
    img0_flipped = _render_synthetic_frame(s0, flipped=True)
    img0_white = _render_synthetic_frame(s0, flipped=False)

    det = BoardDetector()
    r_b = det.process_frame(img0_flipped, side_pref="b")
    assert r_b.status == "ok"
    assert r_b.flipped is True

    r_w = det.process_frame(img0_white, side_pref="w")
    assert r_w.status == "ok"
    assert r_w.flipped is False

    det2 = BoardDetector()
    r2_w = det2.process_frame(img0_white, side_pref="w")
    assert r2_w.flipped is False
    # Live toggle to "b" locks flipped=True immediately
    r2_b = det2.process_frame(img0_flipped, side_pref="b")
    assert r2_b.flipped is True


def test_extract_and_frame_speed_under_25ms_budget():
    import time
    from vision_core.board_detector import _extract_square_observations

    s0 = ChessBoardState.starting_position()
    s1 = s0.push_uci("e2e4")
    img0 = _render_synthetic_frame(s0, width=1920, height=1080, bx=300, by=120, sq=90)
    img1 = _render_synthetic_frame(s1, width=1920, height=1080, bx=300, by=120, sq=90)
    det = BoardDetector()
    r0 = det.process_frame(img0)
    assert r0.bounds is not None
    det.process_frame(img1)  # leave Move-1 verify & warm steady cache
    # Warm extract JIT/CPU cache once, then measure 8 iterations
    _extract_square_observations(img1, r0.bounds, False, None)
    t0 = time.perf_counter()
    for _ in range(8):
        _extract_square_observations(img1, r0.bounds, False, None)
    avg_extract_ms = (time.perf_counter() - t0) * 1000.0 / 8.0
    assert avg_extract_ms < 25.0, f"Extract exceeded 25ms budget: {avg_extract_ms:.2f}ms"
