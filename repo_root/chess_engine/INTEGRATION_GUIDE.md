# Meraki Chess GUI - 拡張機能ドキュメント

## 概要
wxgui.pyに以下の新機能を統合しました：
1. **リソース監視タブ** - CPU、メモリ、GPU使用率の監視とグラフ表示
2. **Stockfish対戦タブ** - Merakiエンジンとの勝率測定機能
3. **統計情報タブ** - 対戦結果の統計表示

## 機能詳細

### 1. リソース監視機能

**タブ: "リソース監視"**

プロセスのリソース使用状況をリアルタイムで監視します。

#### 機能:
- **CPU監視**: プロセスCPU使用率とシステムCPU使用率
- **メモリ監視**: システムメモリ使用率とプロセスRSS（物理メモリ）
- **GPU監視**: GPUユーティリティとメモリ使用量（NVIDIA対応）
- **グラフ表示**: Matplotlibによるリアルタイムグラフ
- **データ保存**: CSV形式でのデータ出力とPNG形式のグラフ出力

#### 使用方法:
1. 監視間隔(ms)と監視時間(s)を設定
2. 「開始」ボタンをクリック
3. リアルタイムでグラフが更新される
4. 「停止」ボタンで監視を停止
5. 「保存」ボタンでデータとグラフを出力

#### 出力ファイル:
- `monitor_out/monitor_YYYYMMDD_HHMMSS.csv` - 時系列データ
- `monitor_out/graphs_YYYYMMDD_HHMMSS.png` - グラフ

### 2. Stockfish対戦機能

**タブ: "Stockfish対戦"**

Merakiエンジンとの自動対戦で勝率を測定します。

#### 機能:
- **複数ゲーム対戦**: 指定数のゲームを自動実行
- **色の交代**: 奇数・偶数ゲームで白黒を入れ替え
- **詳細な統計**: 勝敗数、勝率、スコア、ゲーム時間などを計測
- **ELO差推定**: レーティング差を推定

#### 設定項目:
- **ゲーム数**: 対戦するゲーム数（1～100）
- **Meraki深さ**: Merakiエンジンの探索深さ（1～20）
- **Stockfish深さ**: Stockfishの探索深さ（1～25）
- **Stockfishパス**: Stockfishの実行ファイルパス（デフォルト: "stockfish"）

#### 使用方法:
1. 各パラメータを設定
2. 「対戦開始」ボタンをクリック
3. ログパネルで進行状況を確認
4. 対戦完了後、統計結果が表示される

#### 出力情報:
- 対戦ログ: 各ゲームの結果、手数、実行時間
- 統計結果:
  - 総ゲーム数
  - Meraki勝利数、Stockfish勝利数、引き分け数
  - 勝率（%）
  - スコア（勝点）
  - 平均ゲーム長（手数）
  - 平均ゲーム時間（秒）
  - 推定ELO差

#### 出力ファイル:
- `match_results/match_YYYYMMDD_HHMMSS.csv` - ゲーム詳細情報
- `match_results/stats_YYYYMMDD_HHMMSS.txt` - 統計情報

### 3. 統計情報タブ

**タブ: "統計情報"**

対戦結果の累積統計情報を表示します。複数の対戦セッションの結果を確認できます。

## コマンドライン実行

vs_stockfish.pyをコマンドラインから直接実行することもできます：

```bash
python -m chess_engine.cli.vs_stockfish --games 10 --meraki-depth 5 --stockfish-depth 15 --stockfish /path/to/stockfish
```

### オプション:
- `--games N`: 対戦ゲーム数（デフォルト: 5）
- `--stockfish PATH`: Stockfishのパス（デフォルト: "stockfish"）
- `--meraki-depth N`: Meraki探索深さ（デフォルト: 5）
- `--stockfish-depth N`: Stockfish探索深さ（デフォルト: 15）

## 実装の詳細

### wxgui.py の構成

| タブ | クラス/関数 | 説明 |
|------|-----------|------|
| チェス対戦 | `_build_game_ui()` | 人間 vs Merakiの対戦UI |
| リソース監視 | `_build_monitor_ui()` | リソース監視UI |
|  | `_on_monitor_timer()` | 定期的なデータ収集 |
|  | `_update_monitor_graph()` | グラフの更新 |
| Stockfish対戦 | `_build_match_ui()` | 対戦設定UI |
|  | `_on_match_start()` | 対戦開始処理 |
|  | `_run_match_thread()` | 対戦実行スレッド |
|  | `_update_match_results()` | 結果表示 |
| 統計情報 | `_build_stats_ui()` | 統計表示UI |

### vs_stockfish.py の構成

```python
class EngineMatch:
    - __init__()           # 初期化
    - play_move_meraki()   # Merakiの手を生成
    - play_move_stockfish()# Stockfishの手を生成
    - play_game()          # 1ゲームを実行
    - play_matches()       # 複数ゲームを実行
    - calculate_stats()    # 統計情報を計算
    - save_results()       # 結果をファイル保存
    - close()              # エンジンを終了
```

## 依存ライブラリ

### 必須:
- wxPython >= 4.0
- python-chess
- psutil

### オプション:
- matplotlib (グラフ表示用)
- pynvml (GPU監視用)

## 注意点

1. **Stockfishのパス**: 
   - システムのPATHに登録されていない場合は、フルパスを指定してください
   - Windows: `C:\\stockfish\\stockfish.exe`
   - Linux/Mac: `/usr/bin/stockfish`

2. **パフォーマンス**:
   - 深い探索深さ + ゲーム数が多いと実行時間が長くなります
   - 最初は深さ5-10、ゲーム数5で試してください

3. **GPU監視**:
   - NVIDIAのGPUがある場合のみ機能します
   - `pip install nvidia-ml-py3` でインストール

4. **グラフ表示**:
   - Matplotlibがインストールされていない場合、グラフ機能は無効になります
   - `pip install matplotlib` でインストール

## トラブルシューティング

### Stockfishが見つからない
```
エラー: Stockfishの初期化に失敗しました
→ Stockfishのパスを確認し、正しく指定してください
```

### モニタリングデータが表示されない
```
→ Matplotlibがインストールされているか確認してください
→ `pip install matplotlib` でインストール
```

### GPUが監視されない
```
→ NVIDIAのドライバがインストールされているか確認
→ `pip install nvidia-ml-py3` でインストール
```

## 今後の改善案

1. 複数Stockfishエンジンとの同時対戦
2. 検索木の可視化
3. 局面評価値の表示
4. 時間制限設定の細分化
5. 対戦履歴のデータベース化
6. 棋譜再生機能の拡張

