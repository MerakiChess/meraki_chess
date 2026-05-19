# TODO (Meraki vs Stockfish: Meraki強化)

- [ ] Meraki側の評価関数（chess_engine/eval/heuristic.py）をチューニング/強化する方針を決める
- [x] 評価関数で 'SquareSet.contains' を使っていた箇所を修正（互換性確保）
- [x] 探索（chess_engine/engine/searcher.py）の弱点（time_up時の戻り値、null-move条件、quiescence条件等）を特定する（null-move無効化で切り分け開始）

- [x] 評価関数をフェーズ分岐＋攻め寄り係数で調整（序盤：駒強め/キング寄り、終盤：passed pawn 等）
- [x] move ordering（chess_engine/engine/move_order.py）を改善（check/promotion優先、historyキー精度UP）

- [ ] opening_book の使い方・呼び出しを確認し、最適化する
- [ ] （検証）簡易対戦を回して勝率/探索指標が出るか確認
- [x] vs_stockfish.py のCSV保存（moves_uciがfieldnames外で落ちる件）を修正

- [ ] 変更を反映した後、（可能なら）簡易対戦を回して勝率/探索指標を確認する
- [ ] 追加モード（“鬼つよ”相当）を実装するなら、wxgui.pyw と EngineMatch/CLI に反映する

