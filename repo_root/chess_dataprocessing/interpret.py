# interpret.py
# winner/moves を含む CSV/PGN/フォルダを読み、winnerを1/0化して保存
import argparse
from pathlib import Path
import pandas as pd

NEEDED = ["winner", "moves"]
OPT = ["white_rating", "black_rating"]

def read_csv(p: Path) -> pd.DataFrame:
    return pd.read_csv(p)

def read_pgn(p: Path) -> pd.DataFrame:
    try:
        import chess.pgn
    except ImportError:
        raise SystemExit("[ERROR] PGN読込には `pip install chess` が必要です。")
    rows=[]
    with open(p, "r", encoding="utf-8", errors="ignore") as f:
        while True:
            g = chess.pgn.read_game(f)
            if g is None: break
            res = str(g.headers.get("Result",""))
            if res not in ("1-0","0-1"): continue
            winner = "white" if res=="1-0" else "black"
            node=g; san=[]
            while node.variations:
                node=node.variation(0)
                if node.move: san.append(node.board().san(node.move))
            rows.append({"winner":winner,"moves":" ".join(san)})
    return pd.DataFrame(rows)

def read_any(src: Path) -> pd.DataFrame:
    if src.is_dir():
        parts=[]
        for p in src.rglob("*"):
            if p.suffix.lower()==".csv": parts.append(read_csv(p))
            elif p.suffix.lower()==".pgn": parts.append(read_pgn(p))
        if not parts: raise SystemExit(f"[ERROR] {src} に CSV/PGN が見つかりません。")
        return pd.concat(parts, ignore_index=True)
    if src.suffix.lower()==".csv": return read_csv(src)
    if src.suffix.lower()==".pgn": return read_pgn(src)
    raise SystemExit(f"[ERROR] 未対応拡張子: {src.suffix}（CSV/PGN/フォルダに対応）")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", default="data/games_clean.csv")
    args=ap.parse_args()

    src=Path(args.inp); out=Path(args.out)
    if not src.exists(): raise SystemExit(f"[ERROR] 入力が見つかりません: {src}")

    df = read_any(src)
    miss=[c for c in NEEDED if c not in df.columns]
    if miss: raise SystemExit(f"[ERROR] 必須列が不足: {miss}")

    df = df[df["winner"].isin(["white","black"])].copy()
    df["winner"] = df["winner"].map({"white":1,"black":0}).astype("int8")
    cols=[c for c in (NEEDED+OPT) if c in df.columns]
    df = df[cols]

    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False, encoding="utf-8")
    print(f"[OK] cleaned -> {out}  rows={len(df)}  cols={list(df.columns)}")
    print("ウバーレ、ポリエあと忘れた")

if __name__=="__main__":
    main()
