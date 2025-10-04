from __future__ import annotations
from typing import Optional, List, Dict, Tuple
import chess


class MoveOrderer:
    """TT move > captures (MVV-LVA) > killers > history."""

    def __init__(self) -> None:
        self.killers: List[Tuple[Optional[chess.Move], Optional[chess.Move]]] = [
            (None, None) for _ in range(256)
        ]
        self.history: Dict[Tuple[int, int], int] = {}

    @staticmethod
    def mvv_lva(board: chess.Board, move: chess.Move) -> int:
        if not board.is_capture(move):
            return 0
        att = board.piece_at(move.from_square)
        vic = board.piece_at(move.to_square)
        # EP victim is a pawn of opposite color.
        if vic is None and board.is_en_passant(move):
            vic = chess.Piece(chess.PAWN, not board.turn)
        v = 100 * (vic.piece_type if vic else 0)
        a = att.piece_type if att else 0
        return v - a

    def order(
        self,
        board: chess.Board,
        moves: List[chess.Move],
        tt_move: Optional[chess.Move],
        ply: int,
    ) -> List[chess.Move]:
        km0, km1 = self.killers[ply]

        def score(m: chess.Move) -> int:
            s = 0
            if tt_move and m == tt_move:
                s += 10_000_000
            if board.is_capture(m):
                s += 1_000_000 + self.mvv_lva(board, m)
            if km0 and m == km0:
                s += 100_000
            if km1 and m == km1:
                s += 90_000
            s += self.history.get((int(board.turn), m.to_square), 0)
            return s

        return sorted(moves, key=score, reverse=True)

    def push_killer(self, ply: int, move: chess.Move) -> None:
        a, b = self.killers[ply]
        if a != move:
            self.killers[ply] = (move, a)

    def add_history(self, board: chess.Board, move: chess.Move, depth: int) -> None:
        key = (int(board.turn), move.to_square)
        self.history[key] = self.history.get(key, 0) + depth * depth  # why: stability
