# Chess Engine (Search-only, logistic-coeff ready)
- 最善手探索に特化（学習は別Repo）。  
- 係数ファイル `models/logreg_coeffs.json` があれば **material5** 特徴で勝率→cp に変換・ブレンド。  
- 無ければ手作り評価のみで動作。
