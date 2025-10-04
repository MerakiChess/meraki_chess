from __future__ import annotations
from typing import Dict
import chess

# Piece values (centipawns)
PIECE_VALUES: Dict[int, int] = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 0,
}

# Minimal PSQT (middlegame) for illustration. 64-length lists per piece.
# why: keep simple & deterministic; not tuned.
PSQT_ZERO = [0] * 64

PSQT: Dict[int, list[int]] = {
    chess.PAWN: PSQT_ZERO,
    chess.KNIGHT: PSQT_ZERO,
    chess.BISHOP: PSQT_ZERO,
    chess.ROOK: PSQT_ZERO,
    chess.QUEEN: PSQT_ZERO,
    chess.KING: PSQT_ZERO,
}


def _material(board: chess.Board) -> int:
    score = 0
    for pt, v in PIECE_VALUES.items():
        score += v * (len(board.pieces(pt, chess.WHITE)) - len(board.pieces(pt, chess.BLACK)))
    return score


def _psqt(board: chess.Board) -> int:
    s = 0
    for pt, table in PSQT.items():
        for sq in board.pieces(pt, chess.WHITE):
            s += table[sq]
        for sq in board.pieces(pt, chess.BLACK):
            s -= table[chess.square_mirror(sq)]
    return s


def evaluate_board(board: chess.Board) -> int:
    """Centipawn evaluation from White's POV."""
    if board.is_checkmate():
        # Near-mate scores are handled in search using ply.
        return -100_000
    if (
        board.is_stalemate()
        or board.is_repetition(2)
        or board.is_insufficient_material()
        or board.is_fifty_moves()
    ):
        return 0
    score = _material(board) + _psqt(board)
    return score if board.turn == chess.WHITE else -score
