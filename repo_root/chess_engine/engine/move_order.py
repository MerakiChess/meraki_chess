from future import annotations
from typing import Optional, List, Dict, Tuple
import chess

class MoveOrderer:
def init(self)->None:
self.killers:List=[[None,None] for _ in range(256)]
self.history:Dict={}
def mvv_lva(self,b:chess.Board,m:chess.Move)->int:
if not b.is_capture(m): return 0
att=b.piece_at(m.from_square); vic=b.piece_at(m.to_square)
if vic is None and b.is_en_passant(m): vic=chess.Piece(chess.PAWN, not b.turn)
v=100*(vic.piece_type if vic else 0); a=att.piece_type if att else 0
return v-a
def order(self,b:chess.Board,moves:List,tt_move:Optional,ply:int)->List[chess.Move]:
killers=self.killers[ply]
def score(m:chess.Move)->int:
s=0
if tt_move and m==tt_move: s+=10_000_000
if b.is_capture(m): s+=1_000_000 + self.mvv_lva(b,m)
if killers[0] and m==killers[0]: s+=100_000
if killers[1] and m==killers[1]: s+=90_000
s+= self.history.get((int(b.turn), m.to_square),0)
return s
return sorted(moves, key=score, reverse=True)