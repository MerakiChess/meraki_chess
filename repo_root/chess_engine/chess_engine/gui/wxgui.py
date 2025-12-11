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
    def __init__(self, parent, board: chess.Board):
        super().__init__(parent)
        self.board = board
        self.selected_square = None
        self.legal_moves = []
        self.parent = parent

        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_LEFT_DOWN, self.on_click)

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
                    mv.to_square for mv in self.board.legal_moves if mv.from_square == sq
                ]
        else:
            # 移動試行
            move = chess.Move(self.selected_square, sq)
            if move in self.board.legal_moves:
                self.parent.push_move(move)
            self.selected_square = None
            self.legal_moves = []

        self.Refresh()


class MainFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title="Meraki Chess GUI (wxPython)", size=(600, 600))
        self.board = chess.Board()
        self.move_stack = []

        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        # ボタン類
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        undo_btn = wx.Button(panel, label="⟲ Undo")
        undo_btn.Bind(wx.EVT_BUTTON, self.on_undo)
        hbox.Add(undo_btn)

        vbox.Add(hbox, flag=wx.EXPAND | wx.ALL, border=5)

        # チェス盤
        self.board_panel = ChessBoardPanel(panel, self.board)
        self.board_panel.SetMinSize((SQUARE_SIZE * 8, SQUARE_SIZE * 8))
        vbox.Add(self.board_panel, flag=wx.EXPAND | wx.ALL, border=5)

        panel.SetSizer(vbox)
        self.Show()

    # ========== 人間の手を処理 ==========
    def push_move(self, move):
        self.move_stack.append(self.board.fen())
        self.board.push(move)
        self.board_panel.Refresh()
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
        move = chess.Move.from_uci(mv_uci)

        self.move_stack.append(self.board.fen())
        self.board.push(move)
        self.board_panel.Refresh()

    # ========== Undo ==========
    def on_undo(self, event):
        if not self.move_stack:
            return

        # 1手戻す（AIと人間をまとめて2手戻し）
        if len(self.move_stack) >= 2:
            self.move_stack.pop()
            prev_fen = self.move_stack.pop()
        else:
            prev_fen = self.move_
