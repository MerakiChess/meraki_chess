from __future__ import annotations
from typing import Union
import chess


def to_board(fen_or_startpos: Union[str, chess.Board]) -> chess.Board:
    if isinstance(fen_or_startpos, chess.Board):
        return fen_or_startpos
    s = str(fen_or_startpos).strip().lower()
    if s in ("start", "startpos", "default"):
        return chess.Board()
    return chess.Board(str(fen_or_startpos))
