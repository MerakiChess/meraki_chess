# Chess dataprocessing (logistic-coeff into .json)

# 仮想環境 + 依存
cd C:\Users\kurisuke\Documents\meraki_chess\repo_root\chess_dataprocessing
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip setuptools wheel
python -m pip install chess pandas scikit-learn tqdm

# 1) winner/moves を整える
python interpret.py --in ".\data\games.csv" --out ".\data\games_clean.csv"

# 2) 途中局面をサンプリング（material差分）
python interpret2.py --in ".\data\games_clean.csv" --out ".\data\processed_positions.csv"

# 3) 列名/欠損を最終チェック
python interpret3.py --in ".\data\processed_positions.csv" --out ".\data\processed_positions_cleaned.csv"

# 4) ロジスティック回帰（GPU無でもCPUに自動フォールバック）
python learning.py --in ".\data\processed_positions_cleaned.csv" --out ".\models\logreg_coeffs.json"
