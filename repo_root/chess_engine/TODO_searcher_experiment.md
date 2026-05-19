# TODO: searcher弱点特定（null-move起点）

## 目標
- searcher.py の null-move pruning が棋力/安定性に悪影響を出していないかを切り分ける

## 手順
1. null-move を無効化/有効化を切り替えるフラグを Searcher に追加
2. 両方で同じ局面に対する bestmove が極端に変わるか確認
3. time_up() が発火した局面の評価値が 0 になっていないかも併せて確認
4. 有効な/無効なときの差が大きい場合は、null-move 条件（endgame判定/削減量r）を調整する

