import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from vision_core.chess_rules import ChessBoardState, sq_name, parse_sq


def test_starting_position_fen_and_legal_move_count():
    st = ChessBoardState.starting_position()
    assert st.to_fen() == "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    assert len(st.legal_moves()) == 20


def test_push_uci_handles_ep_castling_and_promotion():
    st = ChessBoardState.starting_position()
    for m in ("e2e4", "a7a6", "e4e5", "d7d5"):
        st = st.push_uci(m)
    assert st.ep == parse_sq("d6")
    assert "e5d6" in st.legal_moves()

    ep_next = st.push_uci("e5d6")
    assert ep_next.board[parse_sq("d5")] == ""
    assert ep_next.board[parse_sq("d6")] == "P"
    assert st.changed_squares_after_move("e5d6") == {parse_sq("e5"), parse_sq("d6"), parse_sq("d5")}

    castle_st = ChessBoardState.from_fen("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    assert "e1g1" in castle_st.legal_moves()
    assert "e1c1" in castle_st.legal_moves()
    after_k_castle = castle_st.push_uci("e1g1")
    assert after_k_castle.board[parse_sq("g1")] == "K"
    assert after_k_castle.board[parse_sq("f1")] == "R"
    assert after_k_castle.board[parse_sq("e1")] == ""
    assert after_k_castle.board[parse_sq("h1")] == ""
    assert after_k_castle.castling == "kq"

    promo_st = ChessBoardState.from_fen("4k3/P7/8/8/8/8/8/4K3 w - - 0 1")
    for suf in ("q", "r", "b", "n"):
        assert f"a7a8{suf}" in promo_st.legal_moves()
    assert promo_st.push_uci("a7a8n").board[parse_sq("a8")] == "N"


def test_pinned_piece_cannot_leave_king_in_check():
    st = ChessBoardState.from_fen("4r2k/8/8/8/8/8/4R3/4K3 w - - 0 1")
    moves = set(st.legal_moves())
    assert "e2e3" in moves
    assert "e2d2" not in moves
    assert "e1d1" in moves
    assert "e1e2" not in moves


def test_infer_move_for_changed_squares_and_highlights():
    st = ChessBoardState.starting_position()
    inferred = st.infer_move_for_changed_squares(
        {parse_sq("e2"), parse_sq("e4")},
        expected_occupant_colors={parse_sq("e2"): "", parse_sq("e4"): "w"},
    )
    assert inferred == ["e2e4"]

    # Highlight speculation handles both normal moves and castling landmarks
    hl_moves = st.infer_move_from_highlights(parse_sq("g1"), parse_sq("f3"))
    assert hl_moves == ["g1f3"]

    castle_st = ChessBoardState.from_fen("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    assert castle_st.infer_move_from_highlights(parse_sq("e1"), parse_sq("h1")) == ["e1g1"]
    assert castle_st.infer_move_from_highlights(parse_sq("e1"), parse_sq("g1")) == ["e1g1"]


def test_to_grid_flipped_orientation():
    st = ChessBoardState.starting_position()
    g_white = st.to_grid(flipped=False)
    assert g_white[7][4] == "K"
    assert g_white[7][3] == "Q"
    assert g_white[0][4] == "k"

    g_black = st.to_grid(flipped=True)
    assert g_black[0][3] == "K"
    assert g_black[0][4] == "Q"
    assert g_black[7][3] == "k"
