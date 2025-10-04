from __future__ import annotations
from typing import Optional, Tuple
import math
import chess

from ..eval.heuristic import evaluate_board as eval_hc
from ..eval.ml_bridge import evaluate_board_with_ml
from .move_order import MoveOrderer
from .time_manager import TimeManager
from .tt import TranspositionTable, TTEntry, EXACT, LOWERBOUND, UPPERBOUND


MATE_SCORE = 100_000
MATE_THRES = 99_000


def _non_pawn_material(board: chess.Board) -> int:
    vals = {chess.KNIGHT: 320, chess.BISHOP: 330, chess.ROOK: 500, chess.QUEEN: 900}
    return sum(
        vals[pt]
        * (len(board.pieces(pt, chess.WHITE)) + len(board.pieces(pt, chess.BLACK)))
        for pt in vals
    )


def _is_endgame(board: chess.Board) -> bool:
    return _non_pawn_material(board) <= 1300


class Searcher:
    def __init__(self, coeff_path: Optional[str] = None, ml_alpha: float = 0.35) -> None:
        self.coeff_path = coeff_path
        self.ml_alpha = ml_alpha
        self.tm = TimeManager()
        self.mo = MoveOrderer()
        self.tt = TranspositionTable()
        self.nodes: int = 0
        self.bestmove: Optional[chess.Move] = None

    # ---------- evaluation ----------
    def evaluate(self, board: chess.Board) -> int:
        if self.coeff_path:
            return evaluate_board_with_ml(board, self.coeff_path, self.ml_alpha)
        return eval_hc(board)

    # ---------- search API ----------
    def search_root(
        self, board: chess.Board, time_ms: Optional[int], depth: int
    ) -> Tuple[Optional[chess.Move], int]:
        self.nodes = 0
        self.bestmove = None
        self.tt.new_age()
        self.tm.start(time_ms)

        alpha, beta = -MATE_SCORE, MATE_SCORE
        best_score = -MATE_SCORE

        for d in range(1, max(1, depth) + 1):
            if self.tm.time_up():
                break
            score = self.negamax(board, d, alpha, beta, 0)
            if self.tm.time_up():
                break
            best_score = score
            # aspiration window (why: stability/ordering)
            alpha = max(-MATE_SCORE, score - 50)
            beta = min(MATE_SCORE, score + 50)

        return (self.bestmove.uci() if self.bestmove else None, best_score)

    # ---------- core search ----------
    def negamax(self, board: chess.Board, depth: int, alpha: int, beta: int, ply: int) -> int:
        if self.tm.time_up():
            return 0
        if board.is_checkmate():
            return -MATE_SCORE + ply
        if (
            board.is_stalemate()
            or board.is_repetition(2)
            or board.is_insufficient_material()
            or board.is_fifty_moves()
        ):
            return 0

        if depth <= 0:
            return self.quiescence(board, alpha, beta, ply)

        self.nodes += 1

        tt_e = self.tt.get(board)
        tt_move = tt_e.best_move if tt_e else None
        if tt_e and tt_e.depth >= depth:
            if tt_e.flag == EXACT:
                return tt_e.score
            if tt_e.flag == LOWERBOUND:
                alpha = max(alpha, tt_e.score)
            elif tt_e.flag == UPPERBOUND:
                beta = min(beta, tt_e.score)
            if alpha >= beta:
                return tt_e.score

        best_score = -MATE_SCORE
        best_move: Optional[chess.Move] = None

        legal_moves = list(board.legal_moves)
        ordered = self.mo.order(board, legal_moves, tt_move, ply)

        for idx, move in enumerate(ordered):
            board.push(move)

            # LMR: late-move reduction for quiet non-check moves
            in_check = board.is_check()
            is_capture = board.is_capture(move)
            reduction = 0
            if (
                depth >= 3
                and idx >= 4
                and not in_check
                and not is_capture
            ):
                reduction = 1

            score = -self.negamax(board, depth - 1 - reduction, -beta, -alpha, ply + 1)

            # If reduced score triggers a raise, re-search full depth.
            if reduction and score > alpha and not self.tm.time_up():
                score = -self.negamax(board, depth - 1, -beta, -alpha, ply + 1)

            board.pop()

            if score > best_score:
                best_score = score
                best_move = move
                if ply == 0:
                    self.bestmove = move
            if best_score > alpha:
                alpha = best_score
            if alpha >= beta:
                # update killers/history on a cutoff
                if not is_capture:
                    self.mo.push_killer(ply, move)
                    self.mo.add_history(board, move, depth)
                break

        # Store in TT
        flag = EXACT
        if best_score <= alpha:
            flag = UPPERBOUND
        elif best_score >= beta:
            flag = LOWERBOUND
        self.tt.store(
            board, TTEntry(depth=depth, score=best_score, flag=flag, best_move=best_move, age=self.tt.age)
        )
        return best_score

    def quiescence(self, board: chess.Board, alpha: int, beta: int, ply: int) -> int:
        if self.tm.time_up():
            return 0
        stand_pat = self.evaluate(board)
        if stand_pat >= beta:
            return beta
        if stand_pat > alpha:
            alpha = stand_pat

        # consider captures and checks
        moves = [m for m in board.legal_moves if board.is_capture(m) or board.gives_check(m)]
        ordered = self.mo.order(board, moves, None, ply)

        for move in ordered:
            board.push(move)
            score = -self.quiescence(board, -beta, -alpha, ply + 1)
            board.pop()

            if score >= beta:
                return beta
            if score > alpha:
                alpha = score
        return alpha


# Convenience API
def find_best_move(
    board: chess.Board,
    depth: int = 6,
    time_ms: Optional[int] = 2000,
    coeff_path: Optional[str] = None,
    ml_alpha: float = 0.35,
) -> Optional[str]:
    searcher = Searcher(coeff_path=coeff_path, ml_alpha=ml_alpha)
    mv, _ = searcher.search_root(board, time_ms=time_ms, depth=depth)
    return mv
