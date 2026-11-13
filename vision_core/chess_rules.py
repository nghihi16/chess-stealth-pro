"""Minimal, exact FIDE chess board state and move-transition solver."""

from __future__ import annotations

from dataclasses import dataclass

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

_KNIGHT_OFFSETS = ((2, 1), (2, -1), (-2, 1), (-2, -1), (1, 2), (1, -2), (-1, 2), (-1, -2))
_KING_OFFSETS = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1))
_BISHOP_DIRS = ((1, 1), (1, -1), (-1, 1), (-1, -1))
_ROOK_DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))
_CASTLE_RIGHTS_ORDER = ("K", "Q", "k", "q")
_CASTLE_ROOK_SQUARES = {7: "K", 0: "Q", 63: "k", 56: "q"}


def parse_sq(name: str) -> int:
    """Convert algebraic square name like 'e2' to 0..63 index (a1=0, h8=63)."""
    s = name.strip().lower()
    if len(s) != 2 or not ("a" <= s[0] <= "h") or not ("1" <= s[1] <= "8"):
        raise ValueError(f"Invalid square: {name!r}")
    return (int(s[1]) - 1) * 8 + (ord(s[0]) - ord("a"))


def sq_name(sq: int) -> str:
    """Convert 0..63 square index (a1=0, h8=63) to algebraic name."""
    rank, file = divmod(sq, 8)
    return f"{chr(ord('a') + file)}{rank + 1}"


def screen_rc_to_sq(row: int, col: int, flipped: bool = False) -> int:
    """Convert screen grid (row 0..7 top-down, col 0..7 left-right) to algebraic sq 0..63."""
    file = (7 - col) if flipped else col
    rank = row if flipped else (7 - row)
    return rank * 8 + file


def sq_to_screen_rc(sq: int, flipped: bool = False) -> tuple[int, int]:
    """Convert algebraic sq 0..63 to screen grid (row 0..7 top-down, col 0..7 left-right)."""
    rank, file = divmod(sq, 8)
    col = (7 - file) if flipped else file
    row = rank if flipped else (7 - rank)
    return row, col


def piece_side(piece: str) -> str:
    """Return 'w', 'b', or '' for a piece character."""
    if not piece:
        return ""
    return "w" if piece.isupper() else "b"


@dataclass(frozen=True)
class ChessBoardState:
    board: tuple[str, ...]
    turn: str = "w"
    castling: str = "KQkq"
    ep: int | None = None
    halfmove: int = 0
    fullmove: int = 1

    @classmethod
    def starting_position(cls) -> "ChessBoardState":
        return cls.from_fen(START_FEN)

    @classmethod
    def from_fen(cls, fen: str) -> "ChessBoardState":
        parts = fen.strip().split()
        if len(parts) < 4:
            raise ValueError(f"Invalid FEN: {fen!r}")
        placement, turn, castling, ep_raw = parts[:4]
        halfmove = int(parts[4]) if len(parts) > 4 else 0
        fullmove = int(parts[5]) if len(parts) > 5 else 1

        ranks = placement.split("/")
        if len(ranks) != 8:
            raise ValueError(f"Invalid FEN placement: {placement!r}")
        squares = [""] * 64
        for idx, rank_str in enumerate(ranks):
            rank = 7 - idx
            file = 0
            for ch in rank_str:
                if ch.isdigit():
                    file += int(ch)
                elif ch.upper() in "PNBRQK" and file < 8:
                    squares[rank * 8 + file] = ch
                    file += 1
                else:
                    raise ValueError(f"Bad FEN character {ch!r} in {fen!r}")
            if file != 8:
                raise ValueError(f"Bad FEN rank width in {fen!r}")

        ep = None if ep_raw == "-" else parse_sq(ep_raw)
        clean_castle = "".join(c for c in _CASTLE_RIGHTS_ORDER if c in castling) or "-"
        return cls(tuple(squares), turn, clean_castle, ep, halfmove, fullmove)

    def to_fen(self) -> str:
        rank_strs = []
        for rank in range(7, -1, -1):
            empties = 0
            out = []
            for file in range(8):
                p = self.board[rank * 8 + file]
                if not p:
                    empties += 1
                else:
                    if empties:
                        out.append(str(empties))
                        empties = 0
                    out.append(p)
            if empties:
                out.append(str(empties))
            rank_strs.append("".join(out))
        ep_s = sq_name(self.ep) if self.ep is not None else "-"
        return f"{'/'.join(rank_strs)} {self.turn} {self.castling} {ep_s} {self.halfmove} {self.fullmove}"

    def to_grid(self, flipped: bool = False) -> list[list[str]]:
        """Return 8x8 list of piece chars indexed [row][col] top-to-bottom on screen."""
        grid = [[""] * 8 for _ in range(8)]
        for row in range(8):
            for col in range(8):
                grid[row][col] = self.board[screen_rc_to_sq(row, col, flipped)]
        return grid

    def king_square(self, side: str) -> int:
        k_char = "K" if side == "w" else "k"
        for i, p in enumerate(self.board):
            if p == k_char:
                return i
        return -1

    def is_square_attacked(self, sq: int, by_side: str) -> bool:
        b = self.board
        rank, file = divmod(sq, 8)
        pawn_dir = -1 if by_side == "w" else 1
        pawn_char = "P" if by_side == "w" else "p"
        pr = rank + pawn_dir
        if 0 <= pr < 8:
            for df in (-1, 1):
                pf = file + df
                if 0 <= pf < 8 and b[pr * 8 + pf] == pawn_char:
                    return True

        knight_char = "N" if by_side == "w" else "n"
        for dr, df in _KNIGHT_OFFSETS:
            nr, nf = rank + dr, file + df
            if 0 <= nr < 8 and 0 <= nf < 8 and b[nr * 8 + nf] == knight_char:
                return True

        king_char = "K" if by_side == "w" else "k"
        for dr, df in _KING_OFFSETS:
            kr, kf = rank + dr, file + df
            if 0 <= kr < 8 and 0 <= kf < 8 and b[kr * 8 + kf] == king_char:
                return True

        queen_char = "Q" if by_side == "w" else "q"
        bishop_char = "B" if by_side == "w" else "b"
        rook_char = "R" if by_side == "w" else "r"

        for dr, df in _BISHOP_DIRS:
            r, f = rank + dr, file + df
            while 0 <= r < 8 and 0 <= f < 8:
                p = b[r * 8 + f]
                if p:
                    if p == bishop_char or p == queen_char:
                        return True
                    break
                r += dr
                f += df

        for dr, df in _ROOK_DIRS:
            r, f = rank + dr, file + df
            while 0 <= r < 8 and 0 <= f < 8:
                p = b[r * 8 + f]
                if p:
                    if p == rook_char or p == queen_char:
                        return True
                    break
                r += dr
                f += df

        return False

    def _apply_unchecked(self, f_sq: int, t_sq: int, prom: str = "") -> "ChessBoardState":
        b = list(self.board)
        moving = b[f_sq]
        captured = b[t_sq]
        kind = moving.upper()
        is_white = moving.isupper()

        b[f_sq] = ""
        if kind == "P" and self.ep is not None and t_sq == self.ep and not captured:
            cap_sq = t_sq - 8 if is_white else t_sq + 8
            b[cap_sq] = ""

        if prom and kind == "P":
            b[t_sq] = prom.upper() if is_white else prom.lower()
        else:
            b[t_sq] = moving

        if kind == "K" and abs((t_sq % 8) - (f_sq % 8)) == 2:
            if t_sq > f_sq:
                b[f_sq + 1] = b[f_sq + 3]
                b[f_sq + 3] = ""
            else:
                b[f_sq - 1] = b[f_sq - 4]
                b[f_sq - 4] = ""

        castle_set = set(self.castling) - {"-"}
        if kind == "K":
            castle_set -= {"K", "Q"} if is_white else {"k", "q"}
        if f_sq in _CASTLE_ROOK_SQUARES:
            castle_set.discard(_CASTLE_ROOK_SQUARES[f_sq])
        if t_sq in _CASTLE_ROOK_SQUARES:
            castle_set.discard(_CASTLE_ROOK_SQUARES[t_sq])
        new_castle = "".join(c for c in _CASTLE_RIGHTS_ORDER if c in castle_set) or "-"

        new_ep = None
        if kind == "P" and abs(t_sq - f_sq) == 16:
            new_ep = (f_sq + t_sq) // 2

        new_half = 0 if (kind == "P" or captured) else (self.halfmove + 1)
        new_full = self.fullmove + (1 if self.turn == "b" else 0)
        return ChessBoardState(
            tuple(b),
            "b" if self.turn == "w" else "w",
            new_castle,
            new_ep,
            new_half,
            new_full,
        )

    def _pseudo_moves(self) -> list[tuple[int, int, str]]:
        b = self.board
        moves: list[tuple[int, int, str]] = []
        side = self.turn
        opp = "b" if side == "w" else "w"
        p_dir = 1 if side == "w" else -1
        start_rank = 1 if side == "w" else 6
        prom_rank = 7 if side == "w" else 0

        for sq, piece in enumerate(b):
            if not piece or piece_side(piece) != side:
                continue
            rank, file = divmod(sq, 8)
            kind = piece.upper()

            if kind == "P":
                nr = rank + p_dir
                if 0 <= nr < 8:
                    fwd = nr * 8 + file
                    if not b[fwd]:
                        if nr == prom_rank:
                            for p_ch in ("q", "r", "b", "n"):
                                moves.append((sq, fwd, p_ch))
                        else:
                            moves.append((sq, fwd, ""))
                            if rank == start_rank:
                                fwd2 = (nr + p_dir) * 8 + file
                                if not b[fwd2]:
                                    moves.append((sq, fwd2, ""))
                    for df in (-1, 1):
                        nf = file + df
                        if 0 <= nf < 8:
                            cap = nr * 8 + nf
                            if (b[cap] and piece_side(b[cap]) == opp) or cap == self.ep:
                                if nr == prom_rank:
                                    for p_ch in ("q", "r", "b", "n"):
                                        moves.append((sq, cap, p_ch))
                                else:
                                    moves.append((sq, cap, ""))
            elif kind == "N":
                for dr, df in _KNIGHT_OFFSETS:
                    nr, nf = rank + dr, file + df
                    if 0 <= nr < 8 and 0 <= nf < 8:
                        tsq = nr * 8 + nf
                        if piece_side(b[tsq]) != side:
                            moves.append((sq, tsq, ""))
            elif kind == "K":
                for dr, df in _KING_OFFSETS:
                    nr, nf = rank + dr, file + df
                    if 0 <= nr < 8 and 0 <= nf < 8:
                        tsq = nr * 8 + nf
                        if piece_side(b[tsq]) != side:
                            moves.append((sq, tsq, ""))
                if side == "w" and sq == 4 and not self.is_square_attacked(4, opp):
                    if "K" in self.castling and not b[5] and not b[6] and b[7] == "R":
                        if not self.is_square_attacked(5, opp) and not self.is_square_attacked(6, opp):
                            moves.append((4, 6, ""))
                    if "Q" in self.castling and not b[1] and not b[2] and not b[3] and b[0] == "R":
                        if not self.is_square_attacked(3, opp) and not self.is_square_attacked(2, opp):
                            moves.append((4, 2, ""))
                elif side == "b" and sq == 60 and not self.is_square_attacked(60, opp):
                    if "k" in self.castling and not b[61] and not b[62] and b[63] == "r":
                        if not self.is_square_attacked(61, opp) and not self.is_square_attacked(62, opp):
                            moves.append((60, 62, ""))
                    if "q" in self.castling and not b[57] and not b[58] and not b[59] and b[56] == "r":
                        if not self.is_square_attacked(59, opp) and not self.is_square_attacked(58, opp):
                            moves.append((60, 58, ""))
            else:
                dirs = _BISHOP_DIRS if kind == "B" else (_ROOK_DIRS if kind == "R" else _KING_OFFSETS)
                for dr, df in dirs:
                    nr, nf = rank + dr, file + df
                    while 0 <= nr < 8 and 0 <= nf < 8:
                        tsq = nr * 8 + nf
                        target = b[tsq]
                        if not target:
                            moves.append((sq, tsq, ""))
                        else:
                            if piece_side(target) == opp:
                                moves.append((sq, tsq, ""))
                            break
                        nr += dr
                        nf += df
        return moves

    def legal_moves(self) -> list[str]:
        side = self.turn
        opp = "b" if side == "w" else "w"
        legal: list[str] = []
        for f_sq, t_sq, prom in self._pseudo_moves():
            nxt = self._apply_unchecked(f_sq, t_sq, prom)
            k_sq = nxt.king_square(side)
            if k_sq >= 0 and not nxt.is_square_attacked(k_sq, opp):
                legal.append(f"{sq_name(f_sq)}{sq_name(t_sq)}{prom}")
        return legal

    def push_uci(self, uci: str) -> "ChessBoardState":
        move_s = uci.strip().lower()
        if move_s not in self.legal_moves():
            raise ValueError(f"Illegal move {uci!r} for FEN {self.to_fen()}")
        f_sq = parse_sq(move_s[:2])
        t_sq = parse_sq(move_s[2:4])
        prom = move_s[4:]
        return self._apply_unchecked(f_sq, t_sq, prom)

    def changed_squares_after_move(self, uci: str) -> set[int]:
        nxt = self.push_uci(uci)
        return {sq for sq in range(64) if self.board[sq] != nxt.board[sq]}

    def infer_move_for_changed_squares(
        self,
        changed_sqs: set[int],
        expected_occupant_colors: dict[int, str] | None = None,
        preferred_prom: str = "q",
    ) -> list[str]:
        """Find legal moves matching exact changed square set (with optional side check)."""
        if not changed_sqs:
            return []
        matches: list[str] = []
        for uci in self.legal_moves():
            if self.changed_squares_after_move(uci) != changed_sqs:
                continue
            if len(uci) == 5 and preferred_prom and uci[4] != preferred_prom:
                continue
            if expected_occupant_colors:
                nxt = self.push_uci(uci)
                if any(piece_side(nxt.board[sq]) != want for sq, want in expected_occupant_colors.items()):
                    continue
            matches.append(uci)
        return matches

    def infer_move_from_highlights(self, sq_a: int, sq_b: int, preferred_prom: str = "q") -> list[str]:
        """Match 2 visually highlighted squares to legal moves (including Chess.com castling highlight)."""
        pair = {sq_a, sq_b}
        if len(pair) != 2:
            return []
        castle_pairs = {
            frozenset((4, 6)): "e1g1",
            frozenset((4, 7)): "e1g1",
            frozenset((4, 2)): "e1c1",
            frozenset((4, 0)): "e1c1",
            frozenset((60, 62)): "e8g8",
            frozenset((60, 63)): "e8g8",
            frozenset((60, 58)): "e8c8",
            frozenset((60, 56)): "e8c8",
        }
        legal = set(self.legal_moves())
        hits: list[str] = []
        castle_hit = castle_pairs.get(frozenset(pair))
        if castle_hit and castle_hit in legal:
            hits.append(castle_hit)

        for uci in sorted(legal):
            f_sq = parse_sq(uci[:2])
            t_sq = parse_sq(uci[2:4])
            if {f_sq, t_sq} == pair:
                if len(uci) == 5 and preferred_prom and uci[4] != preferred_prom:
                    continue
                if uci not in hits:
                    hits.append(uci)
        return hits
