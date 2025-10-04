# interpret3.py
# 欠損・列名を最終チェックして保存（material5 固定）
import argparse
from pathlib import Path
import pandas as pd

NEEDED = ["winner","pawn_diff","bishop_diff","rook_diff","knight_diff","queen_diff"]

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="data/processed_positions.csv")
    ap.add_argument("--out", default="data/processed_positions_cleaned.csv")
    args=ap.parse_args()

    df = pd.read_csv(args.inp)
    if "night_diff" in df.columns and "knight_diff" not in df.columns:
        df.rename(columns={"night_diff":"knight_diff"}, inplace=True)

    missing=[c for c in NEEDED if c not in df.columns]
    if missing:
        raise SystemExit(f"[ERROR] 列不足: {missing}")

    df = df.dropna(subset=NEEDED).copy()
    df = df[NEEDED]
    out=Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False, encoding="utf-8")
    print(f"[OK] cleaned -> {out}  rows={len(df)}")

if __name__=="__main__":
    main()
