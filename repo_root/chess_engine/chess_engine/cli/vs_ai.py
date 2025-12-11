from __future__ import annotations
import argparse
import sys
import chess

from ..io.fen_utils import to_board
from ..engine.searcher import find_best_move
from ..eval.heuristic import evaluate_board as eval_hc
from ..eval.ml_bridge import evaluate_board_with_ml


def _print_board(board: chess.Board) -> None:
    """盤面と FEN を表示する（シンプルな ASCII）。"""
    print()
    print(board)  # デフォルトのテキスト盤面
    print()
    print("FEN:", board.fen())
    print()


def _get_human_move(board: chess.Board) -> chess.Move | None:
    """人間からの入力を受け付ける。

    - SAN 表記 (e4, Nf3, exd5, O-O など)
    - UCI 表記 (e2e4, g1f3 など)
    のどちらでも OK。
    """
    while True:
        mv_str = input("あなたの手を入力してください (SAN または UCI, 'q'で終了): ").strip()
        if mv_str.lower() in ("q", "quit", "exit"):
            return None

        move: chess.Move | None = None
        # まず SAN を試す
        try:
            move = board.parse_san(mv_str)
        except ValueError:
            # 次に UCI を試す
            try:
                move = chess.Move.from_uci(mv_str)
            except ValueError:
                move = None

        if move is None or move not in board.legal_moves:
            print("⚠️ その手は合法手ではありません。もう一度。")
            continue

        return move


def _print_result(board: chess.Board) -> None:
    """終局時の結果表示。"""
    print()
    print("ゲーム終了。")
    print("最終局面:")
    print(board)
    print()

    if board.is_checkmate():
        if board.turn == chess.WHITE:
            print("黒の勝ち（白がチェックメイトされました）")
        else:
            print("白の勝ち（黒がチェックメイトされました）")
    elif board.is_stalemate():
        print("ステイルメイト（引き分け）")
    elif board.is_insufficient_material():
        print("引き分け：十分な駒が残っていません（insufficient material）")
    elif board.is_fivefold_repetition():
        print("引き分け：同一局面が5回出現（fivefold repetition）")
    elif board.is_seventyfive_moves():
        print("引き分け：75手ルール")
    else:
        print("引き分けか、その他の終了条件です。")
    print("結果:", board.result(claim_draw=True))


def main() -> None:
    ap = argparse.ArgumentParser(description="人間 vs AI の対戦用 CLI")
    ap.add_argument("--fen", default="startpos", help="開始局面 (FEN)。'startpos' で初期局面")
    ap.add_argument("--depth", type=int, default=6)
    ap.add_argument("--time-ms", type=int, default=2000)
    ap.add_argument("--coeff", default=None, help="ロジスティック回帰の係数JSONパス")
    ap.add_argument("--alpha", type=float, default=0.35, help="手作り評価とMLのブレンド率 (0〜1)")
    ap.add_argument(
        "--color",
        choices=["white", "black"],
        default="white",
        help="人間が持つ駒の色（white or black）",
    )
    ap.add_argument(
        "--show-eval",
        action="store_true",
        help="各手番で評価値(cp, 白視点)も表示する",
    )

    args = ap.parse_args()

    board = to_board(args.fen)
    human_is_white = (args.color == "white")

    print("=== 人間 vs AI 対戦モード ===")
    print(f"あなたの色: {'白' if human_is_white else '黒'}")
    print(f"探索深さ: {args.depth}, 持ち時間: {args.time_ms} ms, alpha={args.alpha}")
    if args.coeff:
        print(f"ML係数: {args.coeff}")
    print()

    while not board.is_game_over(claim_draw=True):
        _print_board(board)

        # 評価値表示（白視点）
        if args.show_eval:
            cp = (
                evaluate_board_with_ml(board, args.coeff, args.alpha)
                if args.coeff
                else eval_hc(board)
            )
            print(f"評価値（白視点cp）: {cp}")
            print()

        human_turn = (board.turn == chess.WHITE) if human_is_white else (board.turn == chess.BLACK)

        if human_turn:
            print("=== あなたの手番です ===")
            move = _get_human_move(board)
            if move is None:
                print("対局を中断しました。")
                sys.exit(0)
            board.push(move)
        else:
            print("=== AI 考え中... ===")
            mv_uci = find_best_move(
                board,
                depth=args.depth,
                time_ms=args.time_ms,
                coeff_path=args.coeff,
                ml_alpha=args.alpha,
            )
            if mv_uci is None:
                print("AI が指し手を見つけられませんでした。ゲームを終了します。")
                break

            move = chess.Move.from_uci(mv_uci)
            san = board.san(move)
            print(f"AI の指し手: {san} ({mv_uci})")
            board.push(move)

    # 終局処理
    _print_result(board)


if __name__ == "__main__":
    main()
