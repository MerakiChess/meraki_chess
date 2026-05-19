from __future__ import annotations
from typing import Dict
import chess

PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 0,
}

# フェーズ（簡易）
# 盤上の非ポーン駒数から「序盤/終盤」を推定する
ENDGAME_NON_PAWN_PIECES = 7

# 攻め寄りにするための基本係数（後でフェーズで上書き）
K_MOB = 0.07
K_ATT = 0.13

# 終盤はポーン推進・ビショップ/ポーン連動を強め、過度なモビリティを抑える
K_MOB_END = 0.04
K_ATT_END = 0.08

# passed pawn の係数（フェーズで切替）
PASSED_PAWN_K = 26
PASSED_PAWN_K_END = 40


PSQT_PAWN = [0,0,0,0,0,0,0,0, 50,50,50,50,50,50,50,50, 10,10,20,30,30,20,10,10, 5,5,10,25,25,10,5,0, 0,0,0,20,20,0,0,0, 5,-5,-10,0,0,-10,-5,5, 5,10,10,-20,-20,10,10,5, 0,0,0,0,0,0,0,0]

PSQT_KNIGHT = [-50,-40,-30,-30,-30,-30,-40,-50, -40,-20,0,0,0,0,-20,-40, -30,0,10,15,15,10,0,-30, -30,5,15,20,20,15,5,-30, -30,0,15,20,20,15,0,-30, -30,5,10,15,15,10,5,-30, -40,-20,0,5,5,0,-20,-40, -50,-40,-30,-30,-30,-30,-40,-50]

PSQT_BISHOP = [-20,-10,-10,-10,-10,-10,-10,-20, -10,0,0,0,0,0,0,-10, -10,0,5,10,10,5,0,-10, -10,5,5,10,10,5,5,-10, -10,0,10,10,10,10,0,-10, -10,10,10,10,10,10,10,-10, -10,5,0,0,0,0,5,-10, -20,-10,-10,-10,-10,-10,-10,-20]

PSQT_ROOK = [0,0,0,0,0,0,0,0, 5,10,10,10,10,10,10,5, -5,0,0,0,0,0,0,-5, -5,0,0,0,0,0,0,-5, -5,0,0,0,0,0,0,-5, -5,0,0,0,0,0,0,-5, -5,0,0,0,0,0,0,-5, 0,10,10,10,10,10,10,0]

PSQT_QUEEN = [-20,-10,-10,-5,-5,-10,-10,-20, -10,0,0,0,0,0,0,-10, -10,0,5,5,5,5,0,-10, 0,0,5,5,5,5,0,-5, -5,0,5,5,5,5,0,-5, -10,0,5,5,5,5,0,-10, -10,0,0,0,0,0,0,-10, -20,-10,-10,-5,-5,-10,-10,-20]

PSQT_KING = [-30,-40,-40,-50,-50,-40,-40,-30, -30,-40,-40,-50,-50,-40,-40,-30, -30,-40,-40,-50,-50,-40,-40,-30, -30,-40,-40,-50,-50,-40,-40,-30, -20,-30,-30,-40,-40,-30,-30,-20, -10,-20,-20,-20,-20,-20,-20,-10, 20,20,0,0,0,0,20,20, 20,30,10,0,0,10,30,20]

PSQT = {
    chess.PAWN: PSQT_PAWN,
    chess.KNIGHT: PSQT_KNIGHT,
    chess.BISHOP: PSQT_BISHOP,
    chess.ROOK: PSQT_ROOK,
    chess.QUEEN: PSQT_QUEEN,
    chess.KING: PSQT_KING,
}

def _material(board):
    score = 0
    for pt, v in PIECE_VALUES.items():
        score += v * (len(board.pieces(pt, chess.WHITE)) - len(board.pieces(pt, chess.BLACK)))
    return score

def _psqt(board):
    s = 0
    for pt, table in PSQT.items():
        for sq in board.pieces(pt, chess.WHITE):
            s += table[sq]
        for sq in board.pieces(pt, chess.BLACK):
            s -= table[chess.square_mirror(sq)]
    return s

def attack_score(board):
    occupied_white = board.occupied_co[chess.WHITE]
    occupied_black = board.occupied_co[chess.BLACK]
    attacked_black = chess.SquareSet()
    attacked_white = chess.SquareSet()
    for sq in chess.SquareSet(occupied_white):
        attacked_black |= board.attacks(sq) & chess.SquareSet(occupied_black)
    for sq in chess.SquareSet(occupied_black):
        attacked_white |= board.attacks(sq) & chess.SquareSet(occupied_white)
    return len(attacked_black) - len(attacked_white)

def mobility_score(board):
    if board.turn == chess.WHITE:
        b_white = board
        b_black = board.copy(stack=False)
        b_black.turn = chess.BLACK
    else:
        b_white = board.copy(stack=False)
        b_white.turn = chess.WHITE
        b_black = board
    return b_white.legal_moves.count() - b_black.legal_moves.count()

def king_tropism(board, king_sq, piece_type):
    enemies = board.pieces(piece_type, not board.piece_at(king_sq).color)
    return sum(20 // (chess.square_distance(king_sq, sq) + 1) for sq in enemies)

def pawn_passed(board, sq):
    file = chess.square_file(sq)
    color = board.piece_at(sq).color
    direction = 8 if color else -8
    for rank_offset in range(1, 7):
        test_sq = sq + rank_offset * direction
        if test_sq not in chess.SQUARES:
            break
        if test_sq in board.pieces(chess.PAWN, not color):
            return False
    return True

def passed_pawn_bonus(board):
    score = 0
    for sq in board.pieces(chess.PAWN, chess.WHITE):
        rank = chess.square_rank(sq)
        if pawn_passed(board, sq):
            score += 20 * rank
    for sq in board.pieces(chess.PAWN, chess.BLACK):
        rank = 7 - chess.square_rank(sq)
        if pawn_passed(board, sq):
            score -= 20 * rank
    return score

def evaluate_board(board):
    if board.is_checkmate():
        return -100000
    if board.is_game_over():
        return 0

    # フェーズ推定: 非ポーン駒（キング除く）枚数で序盤/終盤を判定
    non_pawn_non_king = (
        len(board.pieces(chess.QUEEN, chess.WHITE)) + len(board.pieces(chess.QUEEN, chess.BLACK)) +
        len(board.pieces(chess.ROOK, chess.WHITE)) + len(board.pieces(chess.ROOK, chess.BLACK)) +
        len(board.pieces(chess.BISHOP, chess.WHITE)) + len(board.pieces(chess.BISHOP, chess.BLACK)) +
        len(board.pieces(chess.KNIGHT, chess.WHITE)) + len(board.pieces(chess.KNIGHT, chess.BLACK))
    )

    is_endgame = non_pawn_non_king <= ENDGAME_NON_PAWN_PIECES

    k_mob = K_MOB_END if is_endgame else K_MOB
    k_att = K_ATT_END if is_endgame else K_ATT

    # 終盤の「必要な駒の連動」を意識して、passed pawnだけでなく
    # 駒交換後に価値が上がる要素（ビショップ/ルークの影響、キングの位置、
    # 盤面の攻撃の質）を少し強める。ポーン連動に寄せすぎない。
    passed_k = PASSED_PAWN_K_END if is_endgame else PASSED_PAWN_K

    # 駒の数に応じて係数をフェーズ補正（より戦略的に）
    num_pieces = len(board.piece_map())
    # 盤上の駒数が少ないほど、キングと軽い駒の連動を優先
    # （駒数が多い序盤は通常のpassed pawnを抑え気味）
    piece_scaler = max(0.0, min(1.0, (20 - num_pieces) / 12))
    # 終盤ほど passed_pawn は強めすぎないよう少し抑制
    passed_k = passed_k * (1.0 - 0.35 * piece_scaler)

    score = _material(board) + _psqt(board)

    mob = mobility_score(board)
    att = attack_score(board)
    score += int(k_mob * mob + k_att * att)
    score += int(passed_k * passed_pawn_bonus(board) / 20)

    wk = board.king(chess.WHITE)
    bk = board.king(chess.BLACK)
    if wk is not None:
        score += king_tropism(board, wk, chess.KNIGHT) + king_tropism(board, wk, chess.BISHOP)
    if bk is not None:
        score -= king_tropism(board, bk, chess.KNIGHT) + king_tropism(board, bk, chess.BISHOP)
    return score if board.turn == chess.WHITE else -score

