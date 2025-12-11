from __future__ import annotations
from typing import Dict
import chess

# Piece values (centipawns)
PIECE_VALUES: Dict[int, int] = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 0,
}

# Mobility and attack weights
K_MOB: float = 0.05
K_ATT: float = 0.10


def attack_score(board: chess.Board) -> int:
    occupied_white = board.occupied_co[chess.WHITE]
    occupied_black = board.occupied_co[chess.BLACK]

    # SquareSet を最初に作る
    attacked_black = chess.SquareSet()
    attacked_white = chess.SquareSet()

    # 白 → 黒
    for sq in chess.SquareSet(occupied_white):
        attacked_black |= board.attacks(sq) & chess.SquareSet(occupied_black)

    # 黒 → 白
    for sq in chess.SquareSet(occupied_black):
        attacked_white |= board.attacks(sq) & chess.SquareSet(occupied_white)

    white_attack = len(attacked_black)
    black_attack = len(attacked_white)

    return white_attack - black_attack



def mobility_score(board: chess.Board) -> int:
    """Return (white_legal_moves - black_legal_moves).

    board を直接書き換えないよう、手番を変えるときは
    copy(stack=False) でコピーしてから turn をいじる。
    """
    # White の合法手数
    if board.turn == chess.WHITE:
        b_white = board
        b_black = board.copy(stack=False)
        b_black.turn = chess.BLACK
    else:
        b_white = board.copy(stack=False)
        b_white.turn = chess.WHITE
        b_black = board

    white_moves = b_white.legal_moves.count()
    black_moves = b_black.legal_moves.count()
    return white_moves - black_moves

# Minimal PSQT (middlegame) for illustration. 64-length lists per piece.
# why: keep simple & deterministic; not tuned.
PSQT_ZERO = [0] * 64

PSQT: Dict[int, list[int]] = {
    chess.PAWN: PSQT_ZERO,
    chess.KNIGHT: PSQT_ZERO,
    chess.BISHOP: PSQT_ZERO,
    chess.ROOK: PSQT_ZERO,
    chess.QUEEN: PSQT_ZERO,
    chess.KING: PSQT_ZERO,
}


def _material(board: chess.Board) -> int:
    score = 0
    for pt, v in PIECE_VALUES.items():
        score += v * (len(board.pieces(pt, chess.WHITE)) - len(board.pieces(pt, chess.BLACK)))
    return score


def _psqt(board: chess.Board) -> int:
    s = 0
    for pt, table in PSQT.items():
        for sq in board.pieces(pt, chess.WHITE):
            s += table[sq]
        for sq in board.pieces(pt, chess.BLACK):
            s -= table[chess.square_mirror(sq)]
    return s


def evaluate_board(board: chess.Board) -> int:
    """Centipawn evaluation from White's POV.

    ベースは「素材 + PSQT（White - Black）」。
    そこに、
    - モビリティ（合法手数の差）
    - 攻撃スコア（敵駒に利きをかけているマスの差）
    を小さい係数で足して、「前に出る」「動ける」手をほんの少し優遇する。
    """
    if board.is_checkmate():
        # Near-mate scores are handled in search using ply.
        return -100_000
    if (
        board.is_stalemate()
        or board.is_repetition(2)
        or board.is_insufficient_material()
        or board.is_fifty_moves()
    ):
        return 0

    # もともとの評価（White - Black）
    score = _material(board) + _psqt(board)

    # アクティビティ項（White - Black）
    mob = mobility_score(board)
    att = attack_score(board)
    score += int(round(K_MOB * mob + K_ATT * att))

    # 返り値は「手番側から見た評価」にする
    return score if board.turn == chess.WHITE else -score
