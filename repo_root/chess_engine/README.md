# Chess Engine (Search-only, logistic-coeff ready)

- 最善手探索に特化（学習は別）。
- 係数ファイル `models/logreg_coeffs.json` があれば **material5** 特徴で勝率→cp に変換し、手作り評価とブレンド。
- 無ければ手作り評価のみ。

# インストール
cd C:\Users\kurisuke\Documents\meraki_chess\repo_root\chess_engine
python -m pip install -U pip
python -m pip install -e .

# 最善手実行

- 手作り評価のみ
python -m chess_engine.cli.play --fen startpos --depth 6 --time-ms 2000

- 学習係数をブレンド（material5）
python -m chess_engine.cli.play --fen startpos --depth 6 --time-ms 2000 --coeff ..\chess_dataprocessing\models\logreg_coeffs.json --alpha 0.35

# ベンチマーク
python -m chess_engine.cli.bench --fen startpos --dmin 4 --dmax 10 --time-ms 2000 --coeff ..\chess_dataprocessing\models\logreg_coeffs.json

# UCIモード
python -c "from chess_engine.io.uci import run_uci; run_uci()"
` 別ウィンドウ/GUIから "position startpos" → "go" → "bestmove ..." を確認 `
`

#仮想環境マニュアル
