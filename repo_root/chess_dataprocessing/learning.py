# learning.py
# material5 でロジスティック回帰（GPU: cuML / CPU: scikit-learn）→ models/logreg_coeffs.json
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd

def train_gpu(X, y):
    from cuml.linear_model import LogisticRegression as cuLR
    import cupy as cp
    Xg=cp.asarray(X.astype(np.float32)); yg=cp.asarray(y.astype(np.int32))
    model=cuLR(max_iter=400, tol=1e-4, fit_intercept=True, penalty="l2", C=1.0)
    model.fit(Xg, yg)
    w = np.asarray(model.coef_).ravel()
    b = float(np.asarray(model.intercept_).ravel()[0])
    return w, b

def train_cpu(X, y):
    from sklearn.linear_model import LogisticRegression
    model = LogisticRegression(max_iter=1000, solver="lbfgs")
    model.fit(X, y)
    w = model.coef_.ravel()
    b = float(model.intercept_.ravel()[0])
    return w, b

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="data/processed_positions_cleaned.csv")
    ap.add_argument("--out", default="models/logreg_coeffs.json")
    args=ap.parse_args()

    df = pd.read_csv(args.inp)
    FEATURES = ["pawn_diff","bishop_diff","rook_diff","knight_diff","queen_diff"]
    X = df[FEATURES].astype(np.float32).values
    y = df["winner"].astype(int).values

    # GPU→CPUの順に試す
    try:
        w, b = train_gpu(X, y)
        used = "GPU(cuML)"
    except Exception:
        w, b = train_cpu(X, y)
        used = "CPU(sklearn)"

    payload = {
        "feature_set": "material5",
        "feature_names": FEATURES,
        "w": [float(v) for v in w],
        "b": float(b),
        "note": f"logistic regression for win prob (trained with {used})"
    }
    out=Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] saved -> {out}  method={used}")

if __name__=="__main__":
    main()
