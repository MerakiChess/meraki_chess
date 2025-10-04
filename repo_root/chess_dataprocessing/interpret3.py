import pandas as pd
from pathlib import Path

IN  = Path("data") / "processed_positions.csv"
OUT = Path("data") / "processed_positions_cleaned.csv"

df = pd.read_csv(IN)
rows_before = len(df)

# 1/0 へ
valid = df["winner"].isin(["white","black"])
df = df[valid].copy()
df["winner"] = df["winner"].map({"white": 1, "black": 0}).astype("int8")

# 列の存在を確認（誤綴の night_diff を補修）
if "night_diff" in df.columns and "knight_diff" not in df.columns:
    df.rename(columns={"night_diff": "knight_diff"}, inplace=True)

need_cols = ["pawn_diff","bishop_diff","rook_diff","knight_diff","queen_diff","winner"]
missing = [c for c in need_cols if c not in df.columns]
if missing:
    raise ValueError(f"必要列が不足: {missing}")

df.to_csv(OUT, index=False)
print(f"[OK] cleaned positions -> {OUT}  rows={len(df)}  (dropped {rows_before - len(df)})")
