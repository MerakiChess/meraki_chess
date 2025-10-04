import json
from pathlib import Path

import numpy as np
import pandas as pd

# GPU対応ロジスティック回帰
from cuml.linear_model import LogisticRegression as cuLogisticRegression
import cupy as cp  # GPU配列ライブラリ
from sklearn.model_selection import train_test_split

IN  = Path("data") / "processed_positions_cleaned.csv"
OUT = Path("models") / "logreg_coeffs.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

df = pd.read_csv(IN)

FEATURES = ["pawn_diff","bishop_diff","rook_diff","knight_diff","queen_diff"]  # 順序を固定
TARGET   = "winner"

X_cpu = df[FEATURES].astype(np.float32).values
y_cpu = df[TARGET].astype(np.int32).values  # 1=white, 0=black

# 学習/評価分割（CPUで分割→GPUに転送）
X_train, X_test, y_train_cpu, y_test_cpu = train_test_split(X_cpu, y_cpu, test_size=0.2, random_state=42, stratify=y_cpu)

X_train_gpu = cp.asarray(X_train)
y_train_gpu = cp.asarray(y_train_cpu)
X_test_gpu  = cp.asarray(X_test)
y_test_gpu  = cp.asarray(y_test_cpu)

# cuML ロジスティック回帰
model = cuLogisticRegression(max_iter=400, tol=1e-4, fit_intercept=True, penalty='l2', C=1.0)
model.fit(X_train_gpu, y_train_gpu)

# テスト精度
acc = float(model.score(X_test_gpu, y_test_gpu))
print(f"Test Accuracy: {acc:.4f}")

# 係数取り出し（shape: (1, n_features)）
w = cp.asnumpy(model.coef_.ravel())      # β (長さ5)
b = float(cp.asnumpy(model.intercept_))  # β0

assert len(w) == len(FEATURES)

payload = {
    "feature_set": "material5",          # ← 探索側が見るスイッチ
    "feature_names": FEATURES,           # 安全のため名前も残す
    "w": [float(v) for v in w],          # list[float]
    "b": b,                              # float
    "note": "logistic regression for win prob: p = sigmoid(w·x + b). x is raw piece-count differences."
}
OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"[OK] saved coefficients -> {OUT}")

# 便利: その場で推論する関数
def evaluate_position(pawn_diff, bishop_diff, rook_diff, knight_diff, queen_diff) -> float:
    x = cp.asarray(np.array([pawn_diff, bishop_diff, rook_diff, knight_diff, queen_diff], dtype=np.float32)).reshape(1, -1)
    proba = float(model.predict_proba(x)[0, 1])  # 1=white勝率
    return proba

print("Example p(win):", evaluate_position(1, 1, -1, 0, 0))

