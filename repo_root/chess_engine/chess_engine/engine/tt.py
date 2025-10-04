from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict
import chess
import chess.polyglot

EXACT, LOWERBOUND, UPPERBOUND = 0, 1, 2


@dataclass
class TTEntry:
    depth: int
    score: int
    flag: int
    best_move: Optional[chess.Move]
    age: int


class TranspositionTable:
    """Simple in-memory TT keyed by zobrist. Age is used for replacement preference."""

    def __init__(self) -> None:
        self._t: Dict[int, TTEntry] = {}
        self.age: int = 0

    @staticmethod
    def key(board: chess.Board) -> int:
        return chess.polyglot.zobrist_hash(board)

    def get(self, board: chess.Board) -> Optional[TTEntry]:
        return self._t.get(self.key(board))

    def store(self, board: chess.Board, entry: TTEntry) -> None:
        k = self.key(board)
        old = self._t.get(k)
        # Prefer deeper or newer entries.
        if old is None or entry.depth > old.depth or entry.age >= old.age:
            self._t[k] = entry

    def new_age(self) -> None:
        self.age += 1
