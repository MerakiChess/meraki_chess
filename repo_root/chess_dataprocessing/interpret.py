import pandas as pd
from pathlib import Path

IN = Path("games.csv")                  # 入力: 原始対局データ
OUT = Path("data") / "games_clean.csv"  # 出力: winner整形のみ

OUT.parent.mkdir(parents=True, exist_ok=True)

usecols = ["winner", "white_rating", "black_rating"]
df = pd.read_csv(IN, usecols=usecols)

# 勝者が white/black のみ採用（draw/その他は除外）
df = df[df["winner"].isin(["white", "black"])].copy()
# 1/0 に変換
df["winner"] = df["winner"].map({"white": 1, "black": 0}).astype("int8")

df.to_csv(OUT, index=False)
print(f"[OK] cleaned -> {OUT}  rows={len(df)}")