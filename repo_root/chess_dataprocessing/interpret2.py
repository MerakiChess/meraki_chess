# interpret2.py
# SAN/一部UCIを安全に解釈しつつ、途中手で複数局面をサンプリング→ material diffs を出力
import argparse
from pathlib import Path
import pandas as pd

def sanitize_tokens(moves_str: str):
    toks = []
    for raw in str(moves_str).split():
        t = raw.replace("...", "")           # 黒手マーク省く
        if t.endswith("."): continue         # 手数 "12." を除外
        if t.replace(".", "").isdigit():     # "12" なども除外
            continue
        toks.append(t)
    return toks

def material_diffs(board):
    import chess
    def diff(pt): return len(board.pieces(pt, chess.WHITE)) - len(board.pieces(pt, chess.BLACK))
    return {
        "pawn_diff":   diff(chess.PAWN),
        "bishop_diff": diff(chess.BISHOP),
        "rook_diff":   diff(chess.ROOK),
        "knight_diff": diff(chess.KNIGHT),
        "queen_diff":  diff(chess.QUEEN),
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="data/games_clean.csv")
    ap.add_argument("--out", default="data/processed_positions.csv")
    ap.add_argument("--max-samples-per-game", type=int, default=10)
    args=ap.parse_args()

    try:
        import chess
    except ImportError:
        raise SystemExit("[ERROR] `pip install chess` が必要です。")

    df = pd.read_csv(args.inp)
    if not {"winner","moves"}.issubset(df.columns):
        raise SystemExit("[ERROR] 入力に winner/moves 列が必要です。")

    rows=[]
    for _, row in df.iterrows():
        winner_bin = int(row["winner"])
        toks = sanitize_tokens(row["moves"])
        if not toks: continue

        board = chess.Board()
        # サンプリング位置（均等目安）
        if args.max_samples_per_game > 0:
            k = max(1, min(args.max_samples_per_game, len(toks)))
            idxs = sorted(set(max(1, i*len(toks)//k) for i in range(1, k+1)))
        else:
            idxs = list(range(1, len(toks)+1))

        mv_count=0
        for tok in toks:
            try:
                # SAN優先、失敗したらUCI解釈を試す
                try:
                    board.push_san(tok)
                except Exception:
                    board.push_uci(tok)
            except Exception:
                break  # その対局はこれ以上進めない
            mv_count += 1
            if mv_count in idxs:
                feat = material_diffs(board)
                rows.append({
                    "winner": winner_bin,
                    **feat,
                })

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out, index=False, encoding="utf-8")
    print(f"[OK] positions -> {out}  rows={len(rows)}")

if __name__=="__main__":
    main()
