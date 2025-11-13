from __future__ import annotations
from typing import Optional, Union
import math, chess
from ..eval.heuristic import evaluate_board as eval_hc
from ..eval.ml_bridge import evaluate_board_with_ml
from .move_order import MoveOrderer
from .time_manager import TimeManager
from .tt import TranspositionTable, TTEntry, EXACT, LOWERBOUND, UPPERBOUND

def _non_pawn_material(b: chess.Board)->int:
    vals={chess.KNIGHT:320,chess.BISHOP:330,chess.ROOK:500,chess.QUEEN:900}
    return sum(vals[pt]*(len(b.pieces(pt,chess.WHITE))+len(b.pieces(pt,chess.BLACK))) for pt in vals)
def _is_endgame(b: chess.Board)->bool: return _non_pawn_material(b)<=1300

class Searcher:
    """反復深化 + αβ + TT + LMR + ヌルムーブ + 静止探索"""
    def __init__(self, coeff_path: Optional[str]=None, ml_alpha:float=0.35)->None:
        self.tt=TranspositionTable(); self.mo=MoveOrderer(); self.tm=TimeManager()
        self.iter=0; self.nodes=0; self.coeff_path=coeff_path; self.ml_alpha=ml_alpha

    # --- 評価 ---
    def evaluate(self,b:chess.Board)->int:
        if self.coeff_path: return evaluate_board_with_ml(b, self.coeff_path, self.ml_alpha)
        return eval_hc(b)

    # --- 静止探索 ---
    def quiescence(self,b:chess.Board,alpha:int,beta:int,ply:int)->int:
        self.nodes+=1
        if self.tm.time_up(): return 0
        stand=self.evaluate(b)
        if stand>=beta: return beta
        if stand>alpha: alpha=stand
        noisy=[m for m in b.legal_moves if b.is_capture(m) or b.gives_check(m)]
        for m in self.mo.order(b, noisy, None, ply):
            b.push(m); sc=-self.quiescence(b,-beta,-alpha,ply+1); b.pop()
            if sc>=beta: return beta
            if sc>alpha: alpha=sc
        return alpha

    # --- Negamax ---
    def negamax(self,b:chess.Board,depth:int,alpha:int,beta:int,ply:int)->int:
        if self.tm.time_up(): return 0
        if depth<=0: return self.quiescence(b,alpha,beta,ply)
        if b.is_checkmate(): return -100_000 + ply
        if b.is_repetition(2) or b.is_fifty_moves() or b.is_insufficient_material(): return 0
        self.nodes+=1

        e=self.tt.get(b); tt_move=None
        if e and e.depth>=depth:
            if e.flag==EXACT: return e.score
            if e.flag==LOWERBOUND: alpha=max(alpha,e.score)
            elif e.flag==UPPERBOUND: beta=min(beta,e.score)
            if alpha>=beta: return e.score
            tt_move=e.best_move

        in_check=b.is_check()
        # Null-move pruning
        if not in_check and depth>=3 and b.legal_moves.count()>0 and not _is_endgame(b):
            b.push(chess.Move.null()); r=2+(depth//4)
            sc=-self.negamax(b, depth-1-r, -beta, -beta+1, ply+1); b.pop()
            if sc>=beta: return beta

        legal=list(b.legal_moves)
        if not legal: return 0
        best=-math.inf; best_move=None; raised=False

        for i,m in enumerate(self.mo.order(b, legal, tt_move, ply)):
            b.push(m); nd=depth-1
            # LMR
            if i>3 and not in_check and not b.is_capture(m) and not b.gives_check(m) and depth>=3:
                red=1+(i//8)
                sc=-self.negamax(b, nd-red, -alpha-1, -alpha, ply+1)
                if sc>alpha: sc=-self.negamax(b, nd, -beta, -alpha, ply+1)
            else:
                sc=-self.negamax(b, nd, -beta, -alpha, ply+1)
            b.pop()
            if sc>best:
                best=sc; best_move=m
                if sc>alpha:
                    alpha=sc; raised=True
                    if alpha>=beta:
                        if not b.is_capture(m):
                            k=self.mo.killers[ply]
                            if k[0]!=m: k[1]=k[0]; k[0]=m
                            self.mo.history[(int(b.turn), m.to_square)] = self.mo.history.get((int(b.turn), m.to_square),0)+depth*depth
                        break

        if best_move is None: return 0
        flag = EXACT if raised and best<beta else (LOWERBOUND if best>=beta else UPPERBOUND)
        self.tt.store(b, TTEntry(depth=depth, score=best, flag=flag, best_move=best_move, age=self.iter))
        return best

    # --- 反復深化（外部からはこれだけ呼べばOK） ---
    def search(self,b:chess.Board,max_depth:int,time_ms:Optional[int])->chess.Move:
        """反復深化の本体。bench.py/play.py はこのAPIを使う。"""
        self.tm.start(time_ms); self.nodes=0; self.iter+=1
        best=None; last=self.evaluate(b); window=50
        for d in range(1,max_depth+1):
            if self.tm.time_up(): break
            alpha=last-window; beta=last+window
            for _ in range(3):  # PVS的な窓調整
                sc=self.negamax(b,d,alpha,beta,0)
                if self.tm.time_up(): break
                if sc<=alpha: alpha-=window; window*=2
                elif sc>=beta: beta+=window; window*=2
                else: last=sc; break
            e=self.tt.get(b)
            if e and e.best_move: best=e.best_move
            if best is None: best=next(iter(b.legal_moves), None)
            if best is None: break
        return best or chess.Move.null()

# 既存の外部API（ベンチやCLIはこれでもOK）
def find_best_move(fen_or_board: Union[str,chess.Board], depth:int=6, time_ms:Optional[int]=2000, coeff_path:Optional[str]=None, ml_alpha:float=0.35)->Optional[str]:
    b = fen_or_board if isinstance(fen_or_board,chess.Board) else chess.Board(fen_or_board)
    if b.is_game_over(): return None
    s=Searcher(coeff_path=coeff_path, ml_alpha=ml_alpha)
    m=s.search(b, depth, time_ms)
    return m.uci() if m and m!=chess.Move.null() else None
