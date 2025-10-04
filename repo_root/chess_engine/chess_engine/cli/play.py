from __future__ import annotations
import argparse
import chess

from ..io.fen_utils import to_board
from ..engine.searcher import find_best_move
from ..eval.heuristic import evaluate_board as eval_hc
from ..eval.ml_bridge import evaluate_board_with_ml


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fen", default="startpos")
    ap.add_argument("--depth", type=int, default=6)
    ap.add_argument("--time-ms", type=int, default=2000)
    ap.add_argument("--coeff", default=None, help="models/logreg_coeffs.json")
    ap.add_argument("--alpha", type=float, default=0.35)
    args = ap.parse_args()

    board = to_board(args.fen)
    cp = (
        evaluate_board_with_ml(board, args.coeff, args.alpha)
        if args.coeff
        else eval_hc(board)
    )
    print("FEN:", args.fen)
    print("評価値（白視点cp）:", cp)
    mv = find_best_move(board, depth=args.depth, time_ms=args.time_ms, coeff_path=args.coeff, ml_alpha=args.alpha)
    print("best:", mv)
    if mv:
        print("SAN:", board.san(chess.Move.from_uci(mv)))


if __name__ == "__main__":
    main()
