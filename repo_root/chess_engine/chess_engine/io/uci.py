from __future__ import annotations
import sys
import chess

from ..engine.searcher import find_best_move


def run_uci() -> None:
    print("id name CE-SearchOnly")
    print("id author You")
    print("uciok")
    coeff_path = None
    board = chess.Board()
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        s = line.strip()
        if s == "isready":
            print("readyok")
        elif s == "quit":
            break
        elif s.startswith("setoption name CoeffPath value "):
            coeff_path = s.split("value ", 1)[1].strip()
        elif s.startswith("position"):
            parts = s.split()
            if "startpos" in parts:
                board = chess.Board()
            else:
                i = parts.index("fen")
                fen = " ".join(parts[i + 1 :])
                board = chess.Board(fen)
        elif s.startswith("go"):
            mv = find_best_move(board, depth=6, time_ms=2000, coeff_path=coeff_path)
            print(f"bestmove {mv if mv else '0000'}")
