from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Sequence, List, Dict, Any
import json
import math
import os
import chess
from .heuristic import evaluate_board as eval_hc


@dataclass
class LogRegModel:
    w: Sequence[float]
    b: float
    cp_scale: int = 1200
    feature_set: str = "material5"
    feature_names: Optional[List[str]] = None

    def predict_wp(self, x: Sequence[float]) -> Optional[float]:
        if len(x) != len(self.w):
            return None
        z = float(sum(wi * xi for wi, xi in zip(self.w, x)) + self.b)
        # numerically stable sigmoid
        if z >= 0:
            ez = math.exp(-z)
            p = 1.0 / (1.0 + ez)
        else:
            ez = math.exp(z)
            p = ez / (1.0 + ez)
        return p

    def wp_to_cp(self, p: float) -> int:
        # Map win prob to cp using a simple logistic inverse around 0.5.
        # why: keeps bridge monotonic; cp_scale controls steepness.
        odds = max(1e-9, min(1e9, p / max(1e-9, 1.0 - p)))
        cp = self.cp_scale * math.log(odds)
        return int(round(cp))


def _features_material5(board: chess.Board) -> List[float]:
    def diff(pt: int) -> int:
        return len(board.pieces(pt, chess.WHITE)) - len(board.pieces(pt, chess.BLACK))

    return [
        float(diff(chess.PAWN)),
        float(diff(chess.BISHOP)),
        float(diff(chess.ROOK)),
        float(diff(chess.KNIGHT)),
        float(diff(chess.QUEEN)),
    ]


def _extract_features(board: chess.Board, feature_set: str) -> List[float]:
    if feature_set == "material5":
        return _features_material5(board)
    raise ValueError(f"unknown feature_set: {feature_set}")


def load_model(path: str) -> Optional[LogRegModel]:
    if not path or not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        obj: Dict[str, Any] = json.load(f)
    return LogRegModel(
        w=obj["w"],
        b=obj["b"],
        cp_scale=obj.get("cp_scale", 1200),
        feature_set=obj.get("feature_set", "material5"),
        feature_names=obj.get("feature_names"),
    )


def evaluate_board_with_ml(board: chess.Board, coeff_path: str, alpha: float = 0.35) -> int:
    """Blend handcrafted eval with ML-probability derived cp."""
    hc = eval_hc(board)
    model = load_model(coeff_path)
    if not model:
        return hc
    x = _extract_features(board, model.feature_set)
    p = model.predict_wp(x)
    if p is None:
        return hc
    cp_ml = model.wp_to_cp(p)
    # convex blend
    return int(round((1.0 - alpha) * hc + alpha * cp_ml))
