import chess.pgn
import wx
import wx.lib.scrolledpanel as scrolled
import chess
import chess.engine

from ..engine.searcher import find_best_move
from ..eval.ml_bridge import evaluate_board_with_ml
from ..eval.heuristic import evaluate_board as eval_hc


SQUARE_SIZE = 64
LIGHT_COLOR = wx.Colour(240, 217, 181)
DARK_COLOR = wx.Colour(181, 136, 99)
HIGHLIGHT_COLOR = wx.Colour(170, 210, 130)


class ChessBoardPanel(wx.Panel):
    def __init__(self, parent, board: chess.Board, controller):
        super().__init__(parent)
        self.board = board
        self.selected_square = None
        self.legal_moves = []
        self.controller = controller  # ← ここに MainFrame を保持する

        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_LEFT_DOWN, self.on_click)

    def ask_promotion_piece(self) -> int | None:
        """プロモーション先の駒を選ばせる（QUEEN, ROOK, BISHOP, KNIGHT）。"""
        choices = ["Queen", "Rook", "Bishop", "Knight"]
        dlg = wx.SingleChoiceDialog(
            self,
            message="プロモーションする駒を選んでください",
            caption="Promotion",
            choices=choices,
        )
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return None
            choice = dlg.GetStringSelection()
        finally:
            dlg.Destroy()

        mapping = {
            "Queen": chess.QUEEN,
            "Rook": chess.ROOK,
            "Bishop": chess.BISHOP,
            "Knight": chess.KNIGHT,
        }
        return mapping[choice]

    # ========== 描画 ==========
    def on_paint(self, event):
        dc = wx.PaintDC(self)

        for rank in range(8):
            for file in range(8):
                sq = chess.square(file, 7 - rank)

                # 色
                is_light = (file + rank) % 2 == 0
                color = LIGHT_COLOR if is_light else DARK_COLOR

                if self.selected_square == sq:
                    color = HIGHLIGHT_COLOR
                elif sq in self.legal_moves:
                    color = HIGHLIGHT_COLOR

                dc.SetBrush(wx.Brush(color))
                dc.SetPen(wx.Pen(color))
                dc.DrawRectangle(file * SQUARE_SIZE, rank * SQUARE_SIZE,
                                 SQUARE_SIZE, SQUARE_SIZE)

                # 駒の描画
                piece = self.board.piece_at(sq)
                if piece:
                    label = piece.symbol()
                    dc.SetTextForeground(wx.BLACK if piece.color else wx.WHITE)
                    dc.DrawText(label,
                                file * SQUARE_SIZE + 20,
                                rank * SQUARE_SIZE + 20)

    # ========== マウスクリック処理 ==========
    def on_click(self, event):
        file = event.GetX() // SQUARE_SIZE
        rank = 7 - (event.GetY() // SQUARE_SIZE)
        sq = chess.square(file, rank)

        if self.selected_square is None:
            # 駒選択
            piece = self.board.piece_at(sq)
            if piece and piece.color == self.board.turn:
                self.selected_square = sq
                self.legal_moves = [
                    mv.to_square for mv in self.board.legal_moves
                    if mv.from_square == sq
                ]
        else:
            # 移動試行
            from_sq = self.selected_square
            to_sq = sq
            piece = self.board.piece_at(from_sq)

            move = None

            # ★ プロモーション判定
            if piece and piece.piece_type == chess.PAWN:
                from_rank = chess.square_rank(from_sq)
                to_rank = chess.square_rank(to_sq)

                is_white = piece.color == chess.WHITE
                # 白: rank 6 -> 7, 黒: rank 1 -> 0
                if (is_white and from_rank == 6 and to_rank == 7) or \
                   (not is_white and from_rank == 1 and to_rank == 0):
                    promo_piece = self.ask_promotion_piece()
                    if promo_piece is not None:
                        move = chess.Move(from_sq, to_sq, promotion=promo_piece)
                    else:
                        # キャンセルされたら何もしないで選択解除
                        self.selected_square = None
                        self.legal_moves = []
                        self.Refresh()
                        return

            # 通常手（プロモーションでなければ普通のMoveを作る）
            if move is None:
                move = chess.Move(from_sq, to_sq)

            if move in self.board.legal_moves:
                self.controller.push_move(move)

            self.selected_square = None
            self.legal_moves = []

        self.Refresh()



class MainFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title="Meraki Chess GUI (wxPython)", size=(600, 600))
        self.board = chess.Board()
        self.move_stack = []     # FEN の履歴（待った用）
        self.uci_history = []    # UCI の履歴（PGN保存用）

        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        # ボタン類
        hbox = wx.BoxSizer(wx.HORIZONTAL)

        undo_btn = wx.Button(panel, label="⟲ Undo")
        undo_btn.Bind(wx.EVT_BUTTON, self.on_undo)
        hbox.Add(undo_btn)

        save_btn = wx.Button(panel, label="💾 Save PGN")
        save_btn.Bind(wx.EVT_BUTTON, self.on_save_pgn)
        hbox.Add(save_btn, flag=wx.LEFT, border=5)

        vbox.Add(hbox, flag=wx.EXPAND | wx.ALL, border=5)

        # チェス盤
        self.board_panel = ChessBoardPanel(panel, self.board, controller=self)
        self.board_panel.SetMinSize((SQUARE_SIZE * 8, SQUARE_SIZE * 8))
        vbox.Add(self.board_panel, flag=wx.EXPAND | wx.ALL, border=5)

        panel.SetSizer(vbox)
        self.Show()

    # ========== 人間の手を処理 ==========
    def push_move(self, move: chess.Move):
        # 待った用に現在局面のFENを保存
        self.move_stack.append(self.board.fen())

        # 実際に手を指す
        self.board.push(move)
        self.uci_history.append(move.uci())

        self.board_panel.Refresh()

        # 終局していなければ AI の手番へ
        if not self.board.is_game_over():
            wx.CallLater(50, self.ai_move)


    # ========== AI の手 ==========
    def ai_move(self):
        if self.board.is_game_over():
            return

        mv_uci = find_best_move(
            self.board,
            depth=5,
            time_ms=1500,
            coeff_path=None,
            ml_alpha=0.3,
        )
        if mv_uci is None:
            return

        move = chess.Move.from_uci(mv_uci)

        self.move_stack.append(self.board.fen())
        self.board.push(move)
        self.uci_history.append(move.uci())

        self.board_panel.Refresh()

    # ========== Undo ==========
    def on_undo(self, event):
        if not self.move_stack:
            return

        prev_fen = self.move_stack.pop()
        if self.uci_history:
            self.uci_history.pop()

        self.board = chess.Board(prev_fen)
        self.board_panel.board = self.board
        self.board_panel.Refresh()


    def on_save_pgn(self, event):
        if not self.uci_history:
            wx.MessageBox("まだ一手も指していません。", "情報", wx.OK | wx.ICON_INFORMATION)
            return

        # ファイル保存ダイアログ
        with wx.FileDialog(
            self,
            message="保存する PGN ファイルを選択してください",
            wildcard="PGN files (*.pgn)|*.pgn|All files (*.*)|*.*",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        ) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            path = dlg.GetPath()

        # UCI 履歴から PGN を構成
        game = chess.pgn.Game()
        game.headers["Event"] = "Meraki Chess GUI"
        game.headers["Site"] = "Local"
        game.headers["White"] = "Human"
        game.headers["Black"] = "Engine"
        if self.board.is_game_over():
            game.headers["Result"] = self.board.result()
        else:
            game.headers["Result"] = "*"

        node = game
        board_tmp = chess.Board()  # 初期局面から再生

        for uci in self.uci_history:
            move = board_tmp.parse_uci(uci)
            node = node.add_main_variation(move)
            board_tmp.push(move)

        # ファイルに書き出し
        with open(path, "w", encoding="utf-8") as f:
            print(game, file=f)

        wx.MessageBox(f"PGN を保存しました:\n{path}", "完了", wx.OK | wx.ICON_INFORMATION)



# ==== 起動部分 ====
def main():
    app = wx.App(False)
    MainFrame()
    app.MainLoop()



if __name__ == "__main__":
    main()
