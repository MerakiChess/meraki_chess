from __future__ import annotations
import argparse
import csv
import time
from typing import List, Optional

import chess

from ..engine.searcher import Searcher


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fen", default="startpos")
    ap.add_argument("--dmin", type=int, default=2)
    ap.add_argument("--dmax", type=int, default=8)
    ap.add_argument("--time-ms", type=int, default=2000)
    ap.add_argument("--coeff", default=None)
    ap.add_argument("--alpha", type=float, default=0.35)
    ap.add_argument("--out", default="bench.csv")
    args = ap.parse_args()

    fens: List[str] = [args.fen] if args.fen != "suite" else [
        chess.STARTING_FEN,
        "r1bqkbnr/pppp1ppp/2n5/4p3/3PP3/2N5/PPP2PPP/R1BQKBNR b KQkq - 0 3",
        "r4rk1/1pp1qppp/p1np1n2/2b1p3/2B1P3/P1NP1N2/1PP1QPPP/2KR3R w - - 0 1",
    ]

    rows = []
    for fen in fens:
        board = chess.Board() if fen == "startpos" else chess.Board(fen)
        for d in range(args.dmin, args.dmax + 1):
            se = Searcher(coeff_path=args.coeff, ml_alpha=args.alpha)
            t0 = time.time()
            move, score = se.search_root(board, time_ms=args.time_ms, depth=d)
            elapsed = time.time() - t0
            rows.append(
                {
                    "fen": fen,
                    "depth": d,
                    "time_ms": args.time_ms,
                    "bestmove": move or "",
                    "score": score,
                    "nodes": se.nodes,
                    "nps": int(se.nodes / max(1e-9, elapsed)),
                }
            )
            print(rows[-1])

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"Saved: {args.out}")


if __name__ == "__main__":
    main()
