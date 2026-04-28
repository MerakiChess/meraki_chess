from __future__ import annotations
from typing import Optional, Dict, List, Any
import os, json, random
import chess


class OpeningBook:
    """Simple opening book loader supporting Polyglot (.bin) and JSON fallback.

    JSON format (example):
    {
        "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -": [
            {"move": "e2e4", "weight": 10},
            {"move": "d2d4", "weight": 7}
        ]
    }
    """

    def __init__(self, polyglot_path: Optional[str] = None, json_path: Optional[str] = None) -> None:
        self.polyglot_reader = None
        self.json_book: Dict[str, List[Dict[str, Any]]] = {}
        if polyglot_path and os.path.exists(polyglot_path):
            try:
                import chess.polyglot as polyglot

                self.polyglot_reader = polyglot.open_reader(polyglot_path)
            except Exception:
                self.polyglot_reader = None
        if json_path and os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # normalize keys to the FEN prefix without clocks
                self.json_book = {k: v for k, v in data.items()}
            except Exception:
                self.json_book = {}

    def get(self, board: chess.Board) -> Optional[str]:
        """Return a UCI move string from the book for the given board, or None."""
        # Try polyglot reader first if available
        if self.polyglot_reader:
            try:
                entries = list(self.polyglot_reader.find_all(board))
                if entries:
                    moves = [(e.move.uci(), getattr(e, "weight", 1)) for e in entries]
                    total = sum(w for _, w in moves)
                    r = random.uniform(0, total)
                    upto = 0
                    for mv, w in moves:
                        upto += w
                        if r <= upto:
                            return mv
            except Exception:
                pass

        # Fallback to JSON book; normalize fen (strip move clocks)
        try:
            fen_key = " ".join(board.fen().split(" ")[:4])
            lst = self.json_book.get(fen_key)
            if lst:
                total = sum(int(x.get("weight", 1)) for x in lst)
                r = random.uniform(0, total)
                upto = 0
                for e in lst:
                    w = int(e.get("weight", 1))
                    upto += w
                    if r <= upto:
                        return e.get("move")
        except Exception:
            pass

        return None
