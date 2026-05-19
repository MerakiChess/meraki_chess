import traceback
import chess
from chess_engine.cli.vs_stockfish import EngineMatch

try:
    m = EngineMatch(engine_path='C:/Users/taisei/Downloads/stockfish-windows-x86-64-avx2/stockfish/stockfish-windows-x86-64-avx2.exe', meraki_depth=1, stockfish_depth=1)
    print('EngineMatch created')
    move = m.play_move_meraki(chess.Board())
    print('Meraki move:', move)
except Exception:
    traceback.print_exc()
