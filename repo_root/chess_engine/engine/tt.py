from future import annotations
from dataclasses import dataclass
from typing import Optional, Dict
import chess, chess.polyglot

EXACT, LOWERBOUND, UPPERBOUND = 0,1,2

@dataclass
class TTEntry:
depth:int; score:int; flag:int; best_move:Optional; age:int

class TranspositionTable:
def init(self)->None:
self._t:Dict={}; self.age=0
def key(self,b:chess.Board)->int: return chess.polyglot.zobrist_hash(b)
def get(self,b:chess.Board)->Optional[TTEntry]: return self._t.get(self.key(b))
def store(self,b:chess.Board,e:TTEntry)->None: self._t[self.key(b)]=e