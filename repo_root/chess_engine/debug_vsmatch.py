import traceback
from chess_engine.cli.vs_stockfish import EngineMatch

try:
    match = EngineMatch(engine_path='C:/Users/taisei/Downloads/stockfish-windows-x86-64-avx2/stockfish/stockfish-windows-x86-64-avx2.exe', meraki_depth=5, stockfish_depth=5)
    print('EngineMatch created')
    result = match.play_game(meraki_white=True)
    print('play_game result:', result)
except Exception:
    traceback.print_exc()
