from future import annotations
from typing import Union
import chess

def to_board(fen_or_startpos: Union[str, chess.Board]) -> chess.Board:
if isinstance(fen_or_startpos, chess.Board):
return fen_or_startpos
if str(fen_or_startpos).lower() in ("start","startpos"):
return chess.Board()
return chess.Board(str(fen_or_startpos))