"""
Stockfishとの対戦プログラム
勝率計測とレーティング計算機能付き
"""
import sys
import os

# パスの設定（直接実行時のための相対インポート対応）
if __name__ == "__main__":
    # chess_engineディレクトリの親ディレクトリをパスに追加
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(os.path.dirname(current_dir))
    sys.path.insert(0, parent_dir)

import chess
import chess.engine
import chess.pgn
from typing import Optional, List, Dict, Any, Tuple
import io
import csv
from datetime import datetime
import time
from pathlib import Path
import json

try:
    from ..engine.searcher import find_best_move
    from ..eval.heuristic import evaluate_board as eval_hc
except ImportError:
    # 直接実行時のフォールバック
    try:
        from chess_engine.engine.searcher import find_best_move
        from chess_engine.eval.heuristic import evaluate_board as eval_hc
    except ImportError:
        print("エラー: chess_engineのモジュールをインポートできません")
        print("以下のいずれかの方法で実行してください:")
        print("1. GUIから実行してください（wxgui.pyw）")
        print("2. python -m chess_engine.cli.vs_stockfish で実行")
        sys.exit(1)


class EngineMatch:
    """エンジン同士の対戦を管理するクラス"""
    
    def __init__(self, 
                 engine_path: Optional[str] = None,
                 meraki_depth: int = 5,
                 meraki_time_ms: int = 1500,
                 stockfish_depth: int = 15,
                 stockfish_time_ms: int = 1000,
                 stockfish_skill_level: int = 20,
                 opening_book: Optional[str] = None):
        """
        Args:
            engine_path: Stockfishの実行ファイルパス
            meraki_depth: Merakiエンジンの探索深さ
            meraki_time_ms: Merakiエンジンの思考時間(ms)
            stockfish_depth: Stockfishの探索深さ
            stockfish_time_ms: Stockfishの思考時間(ms)
            stockfish_skill_level: Stockfishの強さレベル(0-20、20が最強)
        """
        self.meraki_depth = meraki_depth
        self.meraki_time_ms = meraki_time_ms
        self.stockfish_depth = stockfish_depth
        self.stockfish_time_ms = stockfish_time_ms
        self.stockfish_skill_level = max(0, min(20, stockfish_skill_level))  # 0-20に制限
        self.opening_book = opening_book
        
        # Stockfishのエンジンを初期化
        if engine_path is None:
            engine_path = "stockfish"  # パスが通っている場合
        
        try:
            self.sf_engine = chess.engine.SimpleEngine.popen_uci(engine_path)
        except Exception as e:
            print(f"警告: Stockfishの初期化に失敗しました: {e}")
            print("パスを確認してください: stockfish.exe or stockfish")
            self.sf_engine = None
    
    def play_move_meraki(self, board: chess.Board) -> Optional[chess.Move]:
        """Merakiエンジンに手を指させる"""
        try:
            uci = find_best_move(
                board,
                depth=self.meraki_depth,
                time_ms=self.meraki_time_ms,
                coeff_path=None,
                ml_alpha=0.0,  # ヒューリスティック評価のみ使用
                opening_book=self.opening_book,
            )
            if uci is None:
                return None
            return chess.Move.from_uci(uci)
        except Exception as e:
            import traceback
            print(f"Merakiエンジンエラー: {e}")
            traceback.print_exc()
            return None
    
    def play_move_stockfish(self, board: chess.Board) -> Optional[chess.Move]:
        """Stockfishに手を指させる"""
        if self.sf_engine is None:
            return None
        try:
            # Skill Levelを設定（0-20）
            self.sf_engine.configure({"Skill Level": self.stockfish_skill_level})
            result = self.sf_engine.play(
                board,
                chess.engine.Limit(depth=self.stockfish_depth, time=self.stockfish_time_ms / 1000.0)
            )
            return result.move
        except Exception as e:
            print(f"Stockfishエラー: {e}")
            return None
    
    def play_game(self, meraki_white: bool = True) -> Tuple[str, List[str], float]:
        """
        1ゲームを実行
        Args:
            meraki_white: Merakiが白の場合True
        Returns:
            (結果, UCI履歴, 実行時間)
        """
        board = chess.Board()
        uci_history = []
        start_time = time.perf_counter()
        
        while not board.is_game_over():
            if board.turn == chess.WHITE:
                if meraki_white:
                    move = self.play_move_meraki(board)
                else:
                    move = self.play_move_stockfish(board)
            else:
                if meraki_white:
                    move = self.play_move_stockfish(board)
                else:
                    move = self.play_move_meraki(board)
            
            if move is None:
                break
            
            board.push(move)
            uci_history.append(move.uci())
        
        elapsed = time.perf_counter() - start_time
        if board.is_game_over():
            result = board.result()
        else:
            result = "*"
        
        return result, uci_history, elapsed
    
    def play_matches(self, num_matches: int = 10, alternate_colors: bool = True) -> Dict[str, Any]:
        """
        複数ゲームを実行して統計を収集
        Args:
            num_matches: マッチ数
            alternate_colors: True の場合、奇数ゲームと偶数ゲームで色を入れ替える
        Returns:
            統計情報を含む辞書
        """
        results = {
            "meraki_wins": 0,
            "stockfish_wins": 0,
            "draws": 0,
            "errors": 0,
            "total_games": 0,
            "games": [],
            "total_time_sec": 0.0,
        }
        
        for i in range(num_matches):
            # 色を交代させる
            meraki_white = (i % 2 == 0) if alternate_colors else True
            
            print(f"ゲーム {i+1}/{num_matches} ... ", end="", flush=True)
            result, uci_history, elapsed = self.play_game(meraki_white)
            
            game_info = {
                "game_num": i + 1,
                "result": result,
                "meraki_white": meraki_white,
                "moves": len(uci_history),
                "time_sec": elapsed,
                "moves_uci": uci_history,  # 手順データを追加
            }
            results["games"].append(game_info)
            results["total_time_sec"] += elapsed
            results["total_games"] += 1
            
            # 結果を更新
            if result == "1-0":  # 白勝利
                if meraki_white:
                    results["meraki_wins"] += 1
                else:
                    results["stockfish_wins"] += 1
            elif result == "0-1":  # 黒勝利
                if meraki_white:
                    results["stockfish_wins"] += 1
                else:
                    results["meraki_wins"] += 1
            elif result == "1/2-1/2":  # 引き分け
                results["draws"] += 1
            else:  # 対局不成立またはエラー
                results["errors"] += 1
            
            print(f"結果: {result}")
        
        return results
    
    def calculate_stats(self, results: Dict[str, Any]) -> Dict[str, float]:
        """
        対戦結果から統計情報を計算
        Args:
            results: play_matches()の戻り値
        Returns:
            統計情報を含む辞書
        """
        total = results["total_games"]
        if total == 0:
            return {}
        
        meraki_wins = results["meraki_wins"]
        draws = results["draws"]
        
        win_rate = (meraki_wins + draws * 0.5) / total
        score = (meraki_wins + draws * 0.5)
        
        # Eloレーティング差の推定（簡易版）
        # スコア率からレーティング差を計算
        if win_rate == 1.0:
            elo_diff = 800
        elif win_rate == 0.0:
            elo_diff = -800
        else:
            elo_diff = 400 * (win_rate - 0.5) / (0.5 if win_rate > 0.5 else -0.5)
            elo_diff = int(elo_diff * 10)  # スケール調整
        
        stats = {
            "meraki_win_rate": round(win_rate * 100, 2),
            "meraki_score": round(score, 1),
            "avg_game_length": round(sum(g["moves"] for g in results["games"]) / total, 1),
            "avg_game_time_sec": round(results["total_time_sec"] / total, 2),
            "estimated_elo_diff": elo_diff,
        }
        
        return stats
    
    def save_results(self, results: Dict[str, Any], output_dir: str = "match_results"):
        """
        対戦結果をCSVファイルに保存
        Args:
            results: play_matches()の戻り値
            output_dir: 出力ディレクトリ
        """
        os.makedirs(output_dir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        csv_path = os.path.join(output_dir, f"match_{stamp}.csv")
        
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "game_num", "result", "meraki_white", "moves", "time_sec", "moves_uci"
            ])
            writer.writeheader()
            writer.writerows(results["games"])
        
        # 統計情報もテキストファイルに保存
        stats = self.calculate_stats(results)
        stats_path = os.path.join(output_dir, f"stats_{stamp}.txt")
        
        with open(stats_path, "w", encoding="utf-8") as f:
            f.write("=== 対戦統計情報 ===\n\n")
            f.write(f"総ゲーム数: {results['total_games']}\n")
            f.write(f"Meraki勝利: {results['meraki_wins']}\n")
            f.write(f"Stockfish勝利: {results['stockfish_wins']}\n")
            f.write(f"引き分け: {results['draws']}\n\n")
            for key, value in stats.items():
                f.write(f"{key}: {value}\n")
        
        print(f"\nCSV保存: {csv_path}")
        print(f"統計情報保存: {stats_path}")
        
        return csv_path, stats_path
    
    def close(self):
        """Stockfishエンジンを終了"""
        if self.sf_engine:
            self.sf_engine.quit()


def run_quick_match(num_games: int = 5, stockfish_path: Optional[str] = None):
    """
    簡単な対戦実行用の関数
    Args:
        num_games: ゲーム数
        stockfish_path: Stockfishのパス
    """
    print(f"\n{'='*50}")
    print(f"Stockfish との対戦を開始します")
    print(f"{'='*50}\n")
    
    match = EngineMatch(
        engine_path=stockfish_path,
        meraki_depth=5,
        meraki_time_ms=1500,
        stockfish_depth=15,
        stockfish_time_ms=1000,
    )
    
    try:
        results = match.play_matches(num_matches=num_games)
        stats = match.calculate_stats(results)
        
        print(f"\n{'='*50}")
        print("対戦結果:")
        print(f"{'='*50}")
        print(f"総ゲーム数: {results['total_games']}")
        print(f"Meraki勝利: {results['meraki_wins']}")
        print(f"Stockfish勝利: {results['stockfish_wins']}")
        print(f"引き分け: {results['draws']}")
        if results.get('errors', 0) > 0:
            print(f"エラー: {results['errors']}")
        print(f"\nMerakiの勝率: {stats['meraki_win_rate']:.1f}%")
        print(f"Merakiのスコア: {stats['meraki_score']:.1f}/{results['total_games']}")
        print(f"平均ゲーム長: {stats['avg_game_length']:.1f} 手")
        print(f"平均ゲーム時間: {stats['avg_game_time_sec']:.2f} 秒")
        print(f"推定ELO差: {stats['estimated_elo_diff']}")
        
        match.save_results(results)
        
    finally:
        match.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Stockfishとの対戦プログラム")
    parser.add_argument("--games", type=int, default=5, help="対戦ゲーム数")
    parser.add_argument("--stockfish", type=str, default=None, help="Stockfishのパス")
    parser.add_argument("--meraki-depth", type=int, default=5, help="Merakiの探索深さ")
    parser.add_argument("--stockfish-depth", type=int, default=15, help="Stockfishの探索深さ")
    
    args = parser.parse_args()
    
    run_quick_match(
        num_games=args.games,
        stockfish_path=args.stockfish,
    )
