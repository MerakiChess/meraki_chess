from future import annotations
from dataclasses import dataclass
from typing import Optional, Sequence, List, Dict, Any
import json, math, os
import chess
from .heuristic import evaluate_board as eval_hc

@dataclass
class LogRegModel:
w: Sequence[float]; b: float; cp_scale:int=1200
feature_set:str="material5"; feature_names:List|None=None
def predict_wp(self,x:Sequence)->Optional[float]:
if len(x)!=len(self.w): return None
z=float(sum(wixi for wi,xi in zip(self.w,x)) + self.b)
if z>=0: ez=math.exp(-z); p=1/(1+ez)
else: ez=math.exp(z); p=ez/(1+ez)
eps=1e-6; return min(1-eps, max(eps,p))
def wp_to_cp(self,p:float)->int:
p=min(1-1e-6, max(1e-6,p)); return int(self.cp_scalemath.log(p/(1-p)))

def load_model(path:str)->Optional[LogRegModel]:
if not os.path.exists(path): return None
try:
d:Dict=json.load(open(path,"r",encoding="utf-8"))
w=d.get("w"); b=d.get("b"); fset=d.get("feature_set","material5"); fn=d.get("feature_names")
if not isinstance(w,(list,tuple)) or not isinstance(b,(int,float)): return None
return LogRegModel([float(x) for x in w], float(b), feature_set=fset, feature_names=fn)
except Exception:
return None

def _features_material5(b: chess.Board)->List[float]:
def diff(pt): return len(b.pieces(pt,chess.WHITE)) - len(b.pieces(pt,chess.BLACK))
return [float(diff(chess.PAWN)), float(diff(chess.BISHOP)), float(diff(chess.ROOK)), float(diff(chess.KNIGHT)), float(diff(chess.QUEEN))]

def _extract_features(b: chess.Board, feature_set:str)->List[float]:
if feature_set=="material5": return _features_material5(b)
raise ValueError(f"unknown feature_set: {feature_set}")

def evaluate_board_with_ml(b: chess.Board, coeff_path:str, alpha:float=0.35)->int:
hc=eval_hc(b)
m=load_model(coeff_path)
if not m: return hc
x=_extract_features(b, m.feature_set)
p=m.predict_wp(x)
if p is None: return hc
cp_ml=m.wp_to_cp(p)
return int(round((1-alpha)hc + alphacp_ml))