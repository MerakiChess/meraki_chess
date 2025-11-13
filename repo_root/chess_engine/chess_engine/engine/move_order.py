from __future__ import annotations
from typing import Optional, List, Dict, Tuple
import chess

class MoveOrderer:
    def __init__(self, max_ply: int = 256) -> None:
        # 可変リスト（代入可能）
        self.killers: List[List[Optional[chess.Move]]] = [[None, None] for _ in range(max_ply)]
        # 履歴ヒューリスティック（color,to_square）→ score
        self.history: Dict[Tuple[int, int], int] = {}

    def note_killer(self, ply: int, move: chess.Move) -> None:
        """βカット発生時の非キャプチャ手をキラーとして記録。"""
        k = self.killers[ply]
        if k[0] != move:
            k[1] = k[0]
            k[0] = move

    def bump_history(self, color: int, to_sq: int, depth: int) -> None:
        """履歴スコアを加点。"""
        key = (color, to_sq)
        self.history[key] = self.history.get(key, 0) + depth * depth

    def mvv_lva(self, b: chess.Board, m: chess.Move) -> int:
        if not b.is_capture(m):
            return 0
        att = b.piece_at(m.from_square)
        vic = b.piece_at(m.to_square)
        if vic is None and b.is_en_passant(m):
            vic = chess.Piece(chess.PAWN, not b.turn)
        v = 100 * (vic.piece_type if vic else 0)
        a = att.piece_type if att else 0
        return v - a

    def order(self, b: chess.Board, moves: List[chess.Move], tt_move: Optional[chess.Move], ply: int) -> List[chess.Move]:
        killers = self.killers[ply]
        def score(m: chess.Move) -> int:
            s = 0
            if tt_move and m == tt_move:
                s += 10_000_000
            if b.is_capture(m):
                s += 1_000_000 + self.mvv_lva(b, m)
            if killers[0] and m == killers[0]:
                s += 100_000
            if killers[1] and m == killers[1]:
                s += 90_000
            s += self.history.get((int(b.turn), m.to_square), 0)
            return s
        return sorted(moves, key=score, reverse=True)
