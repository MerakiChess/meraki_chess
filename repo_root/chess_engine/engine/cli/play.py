from future import annotations
import argparse, chess
from ..io.fen_utils import to_board
from ..engine.searcher import find_best_move
from ..eval.heuristic import evaluate_board as eval_hc
from ..eval.ml_bridge import evaluate_board_with_ml

def main()->None:
ap=argparse.ArgumentParser()
ap.add_argument("--fen", default="startpos")
ap.add_argument("--depth", type=int, default=6)
ap.add_argument("--time-ms", type=int, default=2000)
ap.add_argument("--coeff", default=None, help="models/logreg_coeffs.json")
ap.add_argument("--alpha", type=float, default=0.35)
args=ap.parse_args()
b=to_board(args.fen)
if args.coeff:
cp=evaluate_board_with_ml(b, args.coeff, args.alpha)
else:
cp=eval_hc(b)
print("FEN:", args.fen)
print("評価値（白視点cp）:", cp)
mv=find_best_move(b, depth=args.depth, time_ms=args.time_ms, coeff_path=args.coeff, ml_alpha=args.alpha)
print("best:", mv)
if mv:
m=chess.Move.from_uci(mv)
print("SAN:", b.san(m))

if name=="main":
main()