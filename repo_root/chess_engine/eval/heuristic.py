from future import annotations
from typing import Union
import chess

PIECE_VALUES = {chess.PAWN:100, chess.KNIGHT:320, chess.BISHOP:330, chess.ROOK:500, chess.QUEEN:900, chess.KING:0}

PAWN_MG = [0,0,0,0,0,0,0,0, 50,50,50,50,50,50,50,50, 10,10,20,30,30,20,10,10, 5,5,10,25,25,10,5,5, 0,0,0,20,20,0,0,0, 5,-5,-10,0,0,-10,-5,5, 5,10,10,-20,-20,10,10,5, 0,0,0,0,0,0,0,0]
PAWN_EG = [0]*64
KNIGHT_MG = [-50,-40,-30,-30,-30,-30,-40,-50,-40,-20,0,0,0,0,-20,-40,-30,0,10,15,15,10,0,-30,-30,5,15,20,20,15,5,-30,-30,0,15,20,20,15,0,-30,-30,5,10,15,15,10,5,-30,-40,-20,0,5,5,0,-20,-40,-50,-40,-30,-30,-30,-30,-40,-50]
BISHOP_MG = [-20,-10,-10,-10,-10,-10,-10,-20,-10,5,0,0,0,0,5,-10,-10,10,10,10,10,10,10,-10,-10,0,10,10,10,10,0,-10,-10,5,5,10,10,5,5,-10,-10,0,5,10,10,5,0,-10,-10,0,0,0,0,0,0,-10,-20,-10,-10,-10,-10,-10,-10,-20]
ROOK_MG = [0,0,5,10,10,5,0,0,-5,0,0,0,0,0,0,-5,-5,0,0,0,0,0,0,-5,-5,0,0,0,0,0,0,-5,-5,0,0,0,0,0,0,-5,-5,0,0,0,0,0,0,-5,5,10,10,10,10,10,10,5,0,0,0,0,0,0,0,0]
ROOK_EG = [0,0,5,15,15,5,0,0,5,10,10,10,10,10,10,5,5,10,10,10,10,10,10,5,5,10,10,10,10,10,10,5,5,10,10,10,10,10,10,5,5,10,10,10,10,10,10,5,0,0,5,15,15,5,0,0,0,0,0,0,0,0,0,0]
QUEEN_MG = [-20,-10,-10,-5,-5,-10,-10,-20,-10,0,0,0,0,0,0,-10,-10,0,5,5,5,5,0,-10,-5,0,5,5,5,5,0,-5,0,0,5,5,5,5,0,-5,-10,5,5,5,5,5,0,-10,-10,0,5,0,0,0,0,-10,-20,-10,-10,-5,-5,-10,-10,-20]
KING_MG = [-30,-40,-40,-50,-50,-40,-40,-30,-30,-40,-40,-50,-50,-40,-40,-30,-30,-30,-30,-40,-40,-30,-30,-30,-20,-20,-20,-20,-20,-20,-20,-20,-10,-10,-10,-10,-10,-10,-10,-10,20,20,0,0,0,0,20,20,30,40,10,0,0,10,40,30,20,30,20,0,0,20,30,20]
KING_EG = [-50,-40,-30,-20,-20,-30,-40,-50,-30,-20,-10,0,0,-10,-20,-30,-30,-10,20,30,30,20,-10,-30,-30,-10,30,40,40,30,-10,-30,-30,-10,30,40,40,30,-10,-30,-30,-10,20,30,30,20,-10,-30,-30,-30,0,0,0,0,-30,-30,-50,-30,-30,-30,-30,-30,-30,-50]
PSQT_MG = {chess.PAWN:PAWN_MG, chess.KNIGHT:KNIGHT_MG, chess.BISHOP:BISHOP_MG, chess.ROOK:ROOK_MG, chess.QUEEN:QUEEN_MG, chess.KING:KING_MG}
PSQT_EG = {chess.PAWN:PAWN_EG, chess.KNIGHT:KNIGHT_MG, chess.BISHOP:BISHOP_MG, chess.ROOK:ROOK_EG, chess.QUEEN:QUEEN_MG, chess.KING:KING_EG}

def _material(b: chess.Board)->int:
s=0
for pt,val in PIECE_VALUES.items():
if pt==chess.KING: continue
s += val*(len(b.pieces(pt,chess.WHITE)) - len(b.pieces(pt,chess.BLACK)))
return s

def _psqt(b: chess.Board, mg: bool)->int:
tables = PSQT_MG if mg else PSQT_EG
s=0
for pt,t in tables.items():
for sq in b.pieces(pt,chess.WHITE): s += t[sq]
for sq in b.pieces(pt,chess.BLACK): s -= t[chess.square_mirror(sq)]
return s

def _mobility(b: chess.Board)->int:
wb=b.copy(stack=False); wb.turn=chess.WHITE
bb=b.copy(stack=False); bb.turn=chess.BLACK
return 2*(wb.legal_moves.count() - bb.legal_moves.count())

def _king_safety(b: chess.Board)->int:
def shield(c: chess.Color)->int:
k=b.king(c)
if k is None: return 0
r0=chess.square_rank(k); f0=chess.square_file(k); sc=0
for dr in (-1,0,1):
for df in (-1,0,1):
r=r0+dr; f=f0+df
if 0<=r<=7 and 0<=f<=7:
p=b.piece_at(chess.square(f,r))
if p and p.color==c:
if p.piece_type==chess.PAWN: sc+=5
elif p.piece_type in (chess.KNIGHT,chess.BISHOP): sc+=2
return sc
return shield(chess.WHITE) - shield(chess.BLACK)

def _phase(b: chess.Board)->int:
w={chess.BISHOP:1,chess.KNIGHT:1,chess.ROOK:2,chess.QUEEN:4}
tot=sum(wt*(len(b.pieces(pt,chess.WHITE))+len(b.pieces(pt,chess.BLACK))) for pt,wt in w.items())
return min(24, tot)

def evaluate_board(fen_or_board: Union[str, chess.Board])->int:
b = fen_or_board if isinstance(fen_or_board,chess.Board) else chess.Board(fen_or_board)
if b.is_checkmate(): return -100_000
if b.is_stalemate() or b.is_insufficient_material() or b.is_fifty_moves() or b.can_claim_threefold_repetition(): return 0
mg = _material(b)+_psqt(b,True)+_mobility(b)+_king_safety(b)
eg = _material(b)+_psqt(b,False)+_mobility(b)
ph = _phase(b)
return (mgph + eg(24-ph))//24