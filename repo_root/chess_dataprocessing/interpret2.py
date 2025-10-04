import pandas as pd
import chess
from tqdm import tqdm
from pathlib import Path

IN_GAMES = Path("data") / "games.csv"              # movesとwinnerがあるCSV想定
OUT_POS   = Path("data") / "processed_positions.csv"

OUT_POS.parent.mkdir(parents=True, exist_ok=True)

df = pd.read_csv(IN_GAMES)
assert {"moves","winner"}.issubset(df.columns), "data/games.csv に moves, winner 列が必要です"

records = []
for _, row in tqdm(df.iterrows(), total=len(df)):
    moves_str = str(row["moves"])
    winner_raw = str(row["winner"])
    if winner_raw not in ("white","black"):
        continue
    board = chess.Board()
    moves = moves_str.split()

    # サンプリングする手数インデックス（分割サンプリング）
    indices = [len(moves)//d for d in range(1, 21) if len(moves)//d > 0]
    indices = sorted(set(indices))  # ← ここが元のバグ（.sort未実行）への修正

    mv_count = 0
    for mv in moves:
        try:
            board.push_san(mv)
        except Exception:
            break
        mv_count += 1
        if mv_count in indices:
            def diff(ptype):
                return len(board.pieces(ptype, chess.WHITE)) - len(board.pieces(ptype, chess.BLACK))
            records.append({
                "winner": winner_raw,                 # 後で 1/0 に
                "pawn_diff":   diff(chess.PAWN),
                "bishop_diff": diff(chess.BISHOP),
                "rook_diff":   diff(chess.ROOK),
                "knight_diff": diff(chess.KNIGHT),    # ← night_diff（誤綴）修正
                "queen_diff":  diff(chess.QUEEN),
            })

feature_df = pd.DataFrame.from_records(records)
feature_df.to_csv(OUT_POS, index=False)
print(f"[OK] positions -> {OUT_POS}  rows={len(feature_df)}")
