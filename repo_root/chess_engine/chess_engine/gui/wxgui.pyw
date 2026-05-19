#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
import chess.pgn
import wx
import wx.lib.scrolledpanel as scrolled
import wx.lib.agw.aui as aui
import chess
import chess.engine
import psutil
import time
from datetime import datetime
import os
import csv
import io
from typing import Optional, List, Dict, Any
import threading

from chess_engine.engine.searcher import find_best_move
from chess_engine.eval.ml_bridge import evaluate_board_with_ml
from chess_engine.eval.heuristic import evaluate_board as eval_hc
from chess_engine.cli.vs_stockfish import EngineMatch

# デフォルトのオープニングブック（JSON または polyglot .bin のパス）
DEFAULT_OPENING_BOOK = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'openings.json'))

# GPUサポート（オプション）
try:
    import pynvml # type: ignore
    _HAVE_NVML = True
except Exception:
    _HAVE_NVML = False

try:
    from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigureCanvas
    from matplotlib.figure import Figure
    import matplotlib
    matplotlib.rcParams['font.sans-serif'] = ['MS Gothic', 'Yu Gothic', 'Hiragino Sans']
    matplotlib.rcParams['axes.unicode_minus'] = False
    _HAVE_MATPLOTLIB = True
except Exception:
    _HAVE_MATPLOTLIB = False


SQUARE_SIZE = 64
LIGHT_COLOR = wx.Colour(240, 217, 181)
DARK_COLOR  = wx.Colour(181, 136,  99)
HIGHLIGHT_COLOR = wx.Colour(255, 215,   0) 



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
        super().__init__(None, title="Meraki Chess GUI (wxPython)", size=(1200, 800))
        self.board = chess.Board()
        self.move_stack = []     # FEN の履歴（待った用）
        self.uci_history = []    # UCI の履歴（PGN保存用）
        
        # モニタリング関連
        self.monitor_proc = None
        self.monitor_have_nvml = _init_nvml()
        self.monitor_monitoring = False
        self.monitor_rows: List[Dict[str, Any]] = []
        self.monitor_t0 = 0
        self.monitor_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_monitor_timer, self.monitor_timer)
        
        # 対戦関連
        self.match = None
        self.match_thread = None
        self.match_running = False
        self.match_last_results = None  # 最後の対戦結果を保存

        # メインパネルとノートブック
        notebook = wx.Notebook(self)
        
        # タブ1: チェス対戦
        self.game_panel = wx.Panel(notebook)
        self._build_game_ui(self.game_panel)
        notebook.AddPage(self.game_panel, "チェス対戦")
        
        # タブ2: リソース監視
        self.monitor_panel = wx.Panel(notebook)
        self._build_monitor_ui(self.monitor_panel)
        notebook.AddPage(self.monitor_panel, "リソース監視")
        
        # タブ3: Stockfish対戦
        self.match_panel = wx.Panel(notebook)
        self._build_match_ui(self.match_panel)
        notebook.AddPage(self.match_panel, "Stockfish対戦")
        
        # タブ4: 統計情報
        self.stats_panel = wx.Panel(notebook)
        self._build_stats_ui(self.stats_panel)
        notebook.AddPage(self.stats_panel, "統計情報")
        
        self.Show()

    def _build_game_ui(self, panel):
        vbox = wx.BoxSizer(wx.VERTICAL)

        # ボタン類と設定
        hbox = wx.BoxSizer(wx.HORIZONTAL)

        undo_btn = wx.Button(panel, label="⟲ Undo")
        undo_btn.Bind(wx.EVT_BUTTON, self.on_undo)
        hbox.Add(undo_btn)

        save_btn = wx.Button(panel, label="💾 Save PGN")
        save_btn.Bind(wx.EVT_BUTTON, self.on_save_pgn)
        hbox.Add(save_btn, flag=wx.LEFT, border=5)
        
        new_game_btn = wx.Button(panel, label="🆕 New Game")
        new_game_btn.Bind(wx.EVT_BUTTON, self.on_new_game)
        hbox.Add(new_game_btn, flag=wx.LEFT, border=5)
        
        # AI深さ設定
        hbox.Add(wx.StaticText(panel, label="Meraki強さ (深さ):"), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 15)
        self.game_ai_depth_ctrl = wx.SpinCtrl(panel, initial=18, min=1, max=30)
        hbox.Add(self.game_ai_depth_ctrl, 0, wx.LEFT, 5)

        vbox.Add(hbox, flag=wx.EXPAND | wx.ALL, border=5)

        # チェス盤
        self.board_panel = ChessBoardPanel(panel, self.board, controller=self)
        self.board_panel.SetMinSize((SQUARE_SIZE * 8, SQUARE_SIZE * 8))
        vbox.Add(self.board_panel, flag=wx.EXPAND | wx.ALL, border=5)
        
        # 局面情報
        self.game_info_ctrl = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(-1, 80))
        vbox.Add(wx.StaticText(panel, label="局面情報:"), 0, wx.ALL, 5)
        vbox.Add(self.game_info_ctrl, 0, wx.EXPAND | wx.ALL, border=5)

        panel.SetSizer(vbox)

    def _build_monitor_ui(self, panel):
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # モード選択
        mode_sizer = wx.BoxSizer(wx.HORIZONTAL)
        mode_sizer.Add(wx.StaticText(panel, label="監視モード:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.monitor_mode_choice = wx.Choice(panel, choices=["時間ベース", "深さベース"])
        self.monitor_mode_choice.SetSelection(1)  # デフォルトは深さベース
        self.monitor_mode_choice.Bind(wx.EVT_CHOICE, self._on_monitor_mode_changed)
        mode_sizer.Add(self.monitor_mode_choice, 0, wx.ALL, 5)
        main_sizer.Add(mode_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        # 時間ベース設定パネル
        self.monitor_time_panel = wx.Panel(panel)
        time_sizer = wx.BoxSizer(wx.HORIZONTAL)
        time_sizer.Add(wx.StaticText(self.monitor_time_panel, label="監視間隔 (ms):"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.monitor_interval_ctrl = wx.TextCtrl(self.monitor_time_panel, value="200", size=(100, -1))
        time_sizer.Add(self.monitor_interval_ctrl, 0, wx.ALL, 5)
        time_sizer.Add(wx.StaticText(self.monitor_time_panel, label="監視時間 (s):"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.monitor_duration_ctrl = wx.TextCtrl(self.monitor_time_panel, value="60.0", size=(100, -1))
        time_sizer.Add(self.monitor_duration_ctrl, 0, wx.ALL, 5)
        self.monitor_time_panel.SetSizer(time_sizer)
        main_sizer.Add(self.monitor_time_panel, 0, wx.EXPAND | wx.ALL, 5)
        
        # 深さベース設定パネル
        self.monitor_depth_panel = wx.Panel(panel)
        depth_sizer = wx.BoxSizer(wx.HORIZONTAL)
        depth_sizer.Add(wx.StaticText(self.monitor_depth_panel, label="最小深さ:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.monitor_min_depth_ctrl = wx.SpinCtrl(self.monitor_depth_panel, initial=1, min=1, max=20)
        depth_sizer.Add(self.monitor_min_depth_ctrl, 0, wx.ALL, 5)
        depth_sizer.Add(wx.StaticText(self.monitor_depth_panel, label="最大深さ:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.monitor_max_depth_ctrl = wx.SpinCtrl(self.monitor_depth_panel, initial=12, min=1, max=20)
        depth_sizer.Add(self.monitor_max_depth_ctrl, 0, wx.ALL, 5)
        depth_sizer.Add(wx.StaticText(self.monitor_depth_panel, label="試行回数:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.monitor_trials_ctrl = wx.SpinCtrl(self.monitor_depth_panel, initial=3, min=1, max=10)
        depth_sizer.Add(self.monitor_trials_ctrl, 0, wx.ALL, 5)
        self.monitor_depth_panel.SetSizer(depth_sizer)
        main_sizer.Add(self.monitor_depth_panel, 0, wx.EXPAND | wx.ALL, 5)
        
        # Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.monitor_start_btn = wx.Button(panel, label="開始")
        self.monitor_start_btn.Bind(wx.EVT_BUTTON, self._on_monitor_start)
        btn_sizer.Add(self.monitor_start_btn, 0, wx.ALL, 5)
        self.monitor_stop_btn = wx.Button(panel, label="停止")
        self.monitor_stop_btn.Bind(wx.EVT_BUTTON, self._on_monitor_stop)
        self.monitor_stop_btn.Enable(False)
        btn_sizer.Add(self.monitor_stop_btn, 0, wx.ALL, 5)
        self.monitor_save_btn = wx.Button(panel, label="保存 (CSV & PNG)")
        self.monitor_save_btn.Bind(wx.EVT_BUTTON, self._on_monitor_save)
        btn_sizer.Add(self.monitor_save_btn, 0, wx.ALL, 5)
        main_sizer.Add(btn_sizer, 0, wx.ALL, 5)
        
        # Log
        main_sizer.Add(wx.StaticText(panel, label="ログ:"), 0, wx.ALL, 5)
        self.monitor_log_ctrl = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(-1, 80))
        main_sizer.Add(self.monitor_log_ctrl, 0, wx.EXPAND | wx.ALL, 5)
        
        # Graph
        if _HAVE_MATPLOTLIB:
            main_sizer.Add(wx.StaticText(panel, label="グラフ:"), 0, wx.ALL, 5)
            self.monitor_graph_panel = wx.Panel(panel, size=(-1, 300))
            main_sizer.Add(self.monitor_graph_panel, 1, wx.EXPAND | wx.ALL, 5)
            self._init_monitor_figure()
        else:
            main_sizer.Add(wx.StaticText(panel, label="(Matplotlibが利用できません)"), 0, wx.ALL, 5)
        
        panel.SetSizer(main_sizer)
    
        panel.SetSizer(main_sizer)
    
    def _build_match_ui(self, panel):
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # 設定パネル
        config_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        config_sizer.Add(wx.StaticText(panel, label="ゲーム数:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.match_games_ctrl = wx.SpinCtrl(panel, initial=5, min=1, max=100)
        config_sizer.Add(self.match_games_ctrl, 0, wx.ALL, 5)
        
        config_sizer.Add(wx.StaticText(panel, label="Meraki強さ (深さ):"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.match_meraki_depth_ctrl = wx.SpinCtrl(panel, initial=18, min=1, max=30)
        config_sizer.Add(self.match_meraki_depth_ctrl, 0, wx.ALL, 5)
        
        config_sizer.Add(wx.StaticText(panel, label="Stockfish深さ:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.match_sf_depth_ctrl = wx.SpinCtrl(panel, initial=8, min=1, max=25)
        config_sizer.Add(self.match_sf_depth_ctrl, 0, wx.ALL, 5)
        
        config_sizer.Add(wx.StaticText(panel, label="Stockfish強さ:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.match_sf_skill_ctrl = wx.SpinCtrl(panel, initial=10, min=0, max=20)
        config_sizer.Add(self.match_sf_skill_ctrl, 0, wx.ALL, 5)
        
        main_sizer.Add(config_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        # Stockfishパス設定
        path_sizer = wx.BoxSizer(wx.HORIZONTAL)
        path_sizer.Add(wx.StaticText(panel, label="Stockfishパス:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.match_sf_path_ctrl = wx.TextCtrl(panel, value="stockfish", size=(200, -1))
        path_sizer.Add(self.match_sf_path_ctrl, 1, wx.ALL, 5)
        main_sizer.Add(path_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        # ボタン
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.match_start_btn = wx.Button(panel, label="対戦開始")
        self.match_start_btn.Bind(wx.EVT_BUTTON, self._on_match_start)
        btn_sizer.Add(self.match_start_btn, 0, wx.ALL, 5)
        
        self.match_stop_btn = wx.Button(panel, label="中止")
        self.match_stop_btn.Bind(wx.EVT_BUTTON, self._on_match_stop)
        self.match_stop_btn.Enable(False)
        btn_sizer.Add(self.match_stop_btn, 0, wx.ALL, 5)
        
        self.match_save_btn = wx.Button(panel, label="💾 結果を保存")
        self.match_save_btn.Bind(wx.EVT_BUTTON, self._on_match_save)
        self.match_save_btn.Enable(False)
        btn_sizer.Add(self.match_save_btn, 0, wx.ALL, 5)
        
        main_sizer.Add(btn_sizer, 0, wx.ALL, 5)
        
        # ログ/結果
        main_sizer.Add(wx.StaticText(panel, label="対戦ログ:"), 0, wx.ALL, 5)
        self.match_log_ctrl = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(-1, 150))
        main_sizer.Add(self.match_log_ctrl, 1, wx.EXPAND | wx.ALL, 5)
        
        main_sizer.Add(wx.StaticText(panel, label="統計結果:"), 0, wx.ALL, 5)
        self.match_result_ctrl = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(-1, 150))
        main_sizer.Add(self.match_result_ctrl, 0, wx.EXPAND | wx.ALL, 5)
        
        panel.SetSizer(main_sizer)
    
    def _build_stats_ui(self, panel):
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        main_sizer.Add(wx.StaticText(panel, label="対戦統計情報:"), 0, wx.ALL, 5)
        self.stats_ctrl = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(-1, 150))
        main_sizer.Add(self.stats_ctrl, 0, wx.EXPAND | wx.ALL, 5)
        
        main_sizer.Add(wx.StaticText(panel, label="ゲーム再生:"), 0, wx.ALL, 5)
        
        # ゲーム選択と再生パネル
        replay_panel_sizer = wx.BoxSizer(wx.HORIZONTAL)
        replay_panel_sizer.Add(wx.StaticText(panel, label="ゲーム選択:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.replay_game_choice = wx.Choice(panel)
        replay_panel_sizer.Add(self.replay_game_choice, 1, wx.ALL, 5)
        
        replay_play_btn = wx.Button(panel, label="▶ 再生")
        replay_play_btn.Bind(wx.EVT_BUTTON, self._on_replay_game)
        replay_panel_sizer.Add(replay_play_btn, 0, wx.ALL, 5)
        
        main_sizer.Add(replay_panel_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        # 再生用チェスボード
        self.replay_board_panel = wx.Panel(panel, size=(SQUARE_SIZE * 8, SQUARE_SIZE * 8))
        self.replay_board_panel.SetBackgroundColour(wx.Colour(50, 50, 50))
        main_sizer.Add(wx.StaticText(panel, label="棋譜表示:"), 0, wx.ALL, 5)
        main_sizer.Add(self.replay_board_panel, 0, wx.ALL, 5)
        
        # 手順コントロール
        control_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.replay_prev_btn = wx.Button(panel, label="⏮ 最初")
        self.replay_prev_btn.Bind(wx.EVT_BUTTON, self._on_replay_prev)
        self.replay_prev_btn.Enable(False)
        control_sizer.Add(self.replay_prev_btn, 0, wx.ALL, 5)
        
        self.replay_back_btn = wx.Button(panel, label="◀ 戻す")
        self.replay_back_btn.Bind(wx.EVT_BUTTON, self._on_replay_back)
        self.replay_back_btn.Enable(False)
        control_sizer.Add(self.replay_back_btn, 0, wx.ALL, 5)
        
        self.replay_move_num = wx.StaticText(panel, label="手数: 0/0")
        control_sizer.Add(self.replay_move_num, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        
        self.replay_forward_btn = wx.Button(panel, label="進む ▶")
        self.replay_forward_btn.Bind(wx.EVT_BUTTON, self._on_replay_forward)
        self.replay_forward_btn.Enable(False)
        control_sizer.Add(self.replay_forward_btn, 0, wx.ALL, 5)
        
        self.replay_last_btn = wx.Button(panel, label="最後 ⏭")
        self.replay_last_btn.Bind(wx.EVT_BUTTON, self._on_replay_last)
        self.replay_last_btn.Enable(False)
        control_sizer.Add(self.replay_last_btn, 0, wx.ALL, 5)
        
        main_sizer.Add(control_sizer, 0, wx.ALL, 5)
        
        # PGN表示
        main_sizer.Add(wx.StaticText(panel, label="棋譜（PGN）:"), 0, wx.ALL, 5)
        self.replay_pgn_ctrl = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP, size=(-1, 150))
        main_sizer.Add(self.replay_pgn_ctrl, 1, wx.EXPAND | wx.ALL, 5)
        
        # 再生用の内部状態
        self.replay_board = None
        self.replay_moves = []
        self.replay_current_move = 0
        
        panel.SetSizer(main_sizer)
    
    def _init_monitor_figure(self):
        self.monitor_figure = Figure()
        self.monitor_ax1 = self.monitor_figure.add_subplot(221)  # Process CPU
        self.monitor_ax2 = self.monitor_figure.add_subplot(222)  # System CPU
        self.monitor_ax3 = self.monitor_figure.add_subplot(223)  # Memory
        self.monitor_ax4 = self.monitor_figure.add_subplot(224)  # GPU (if available)
        self.monitor_canvas = FigureCanvas(self.monitor_graph_panel, -1, self.monitor_figure)
        
        # グラフパネルのレイアウト設定
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.monitor_canvas, 1, wx.EXPAND)
        self.monitor_graph_panel.SetSizer(sizer)
    
    def _on_monitor_mode_changed(self, event):
        """監視モード変更時の処理"""
        is_depth_mode = self.monitor_mode_choice.GetSelection() == 1
        self.monitor_time_panel.Show(not is_depth_mode)
        self.monitor_depth_panel.Show(is_depth_mode)
        self.monitor_time_panel.GetParent().Layout()
    
    def _on_monitor_start(self, event):
        """監視開始"""
        is_depth_mode = self.monitor_mode_choice.GetSelection() == 1
        
        if is_depth_mode:
            self._on_monitor_start_depth()
        else:
            self._on_monitor_start_time()
    
    def _on_monitor_start_time(self):
        """時間ベース監視開始"""
        try:
            interval_ms = int(self.monitor_interval_ctrl.GetValue())
            duration_s = float(self.monitor_duration_ctrl.GetValue())
        except ValueError:
            wx.MessageBox("入力値が無効です。", "エラー", wx.ICON_ERROR)
            return
        
        self.monitor_proc = _init_process(None)
        psutil.cpu_percent(None)  # System CPU init
        self.monitor_rows = []
        self.monitor_t0 = time.perf_counter()
        self.monitor_monitoring = True
        self.monitor_start_btn.Enable(False)
        self.monitor_stop_btn.Enable(True)
        self.monitor_timer.Start(interval_ms)
        self.monitor_log_ctrl.AppendText(f"時間ベース監視開始: 間隔={interval_ms}ms, 時間={duration_s}s\n")

    def _on_monitor_start_depth(self):
        """深さベース監視開始"""
        try:
            min_depth = self.monitor_min_depth_ctrl.GetValue()
            max_depth = self.monitor_max_depth_ctrl.GetValue()
            trials = self.monitor_trials_ctrl.GetValue()
        except ValueError:
            wx.MessageBox("入力値が無効です。", "エラー", wx.ICON_ERROR)
            return
        
        if min_depth > max_depth:
            wx.MessageBox("最小深さ > 最大深さです。", "エラー", wx.ICON_ERROR)
            return
        
        self.monitor_start_btn.Enable(False)
        self.monitor_stop_btn.Enable(True)
        self.monitor_monitoring = True  # ★ この行を追加
        self.monitor_log_ctrl.AppendText(f"深さベース監視開始: 深さ={min_depth}-{max_depth}, 試行={trials}\n")
        
        # スレッドで実行
        self.monitor_thread = threading.Thread(
            target=self._run_depth_monitoring,
            args=(min_depth, max_depth, trials),
            daemon=True
        )
        self.monitor_thread.start()
    
    def _run_depth_monitoring(self, min_depth, max_depth, trials):
        """深さベースのリソース監視を実行"""
        try:
            self.monitor_rows = []
            wx.CallAfter(self.monitor_log_ctrl.AppendText, f"スレッド開始: 深さ範囲={min_depth}-{max_depth}, 試行={trials}\n")
            
            for depth in range(min_depth, max_depth + 1):
                if not self.monitor_monitoring:
                    wx.CallAfter(self.monitor_log_ctrl.AppendText, "監視キャンセル\n")
                    break
                
                for trial in range(trials):
                    if not self.monitor_monitoring:
                        break
                    
                    wx.CallAfter(
                        self.monitor_log_ctrl.AppendText,
                        f"深さ {depth}, 試行 {trial+1}/{trials} 実行中... "
                    )
                    
                    try:
                        # リソース監視開始
                        proc = _init_process(None)
                        psutil.cpu_percent(None)
                        
                        t_start = time.perf_counter()
                        rss_start = proc.memory_info().rss / (1024 * 1024)
                        cpu_start = proc.cpu_percent(None)
                        
                        # 初期局面で探索実行
                        board = chess.Board()
                        uci = find_best_move(
                            board,
                            depth=depth,
                            time_ms=5000,  # 最大5秒
                            coeff_path=None,
                            ml_alpha=0.0,
                            opening_book=DEFAULT_OPENING_BOOK,
                        )
                        
                        elapsed = time.perf_counter() - t_start
                        rss_end = proc.memory_info().rss / (1024 * 1024)
                        cpu_end = proc.cpu_percent(None)
                        
                        self.monitor_rows.append({
                            "depth": depth,
                            "trial": trial + 1,
                            "elapsed_sec": round(elapsed, 3),
                            "rss_mb": round(rss_end, 2),
                            "rss_delta_mb": round(rss_end - rss_start, 2),
                            "cpu_percent": round(cpu_end, 2),
                        })
                        
                        wx.CallAfter(
                            self.monitor_log_ctrl.AppendText,
                            f"完了 (時間: {elapsed:.2f}s, メモリ: {rss_end:.1f}MB, CPU: {cpu_end:.1f}%)\n"
                        )
                    except Exception as e:
                        wx.CallAfter(
                            self.monitor_log_ctrl.AppendText,
                            f"エラー: {str(e)}\n"
                        )
                        import traceback
                        wx.CallAfter(
                            self.monitor_log_ctrl.AppendText,
                            f"スタックトレース: {traceback.format_exc()}\n"
                        )
                        continue
            
            wx.CallAfter(self.monitor_log_ctrl.AppendText, f"データ収集完了: {len(self.monitor_rows)}行\n")
            wx.CallAfter(self._update_depth_graph)
            wx.CallAfter(self.monitor_log_ctrl.AppendText, "グラフ更新完了\n")
        except Exception as e:
            wx.CallAfter(self.monitor_log_ctrl.AppendText, f"スレッドエラー: {str(e)}\n")
            import traceback
            wx.CallAfter(self.monitor_log_ctrl.AppendText, f"スタックトレース: {traceback.format_exc()}\n")
        finally:
            self.monitor_monitoring = False
            wx.CallAfter(self.monitor_start_btn.Enable, True)
            wx.CallAfter(self.monitor_stop_btn.Enable, False)
            wx.CallAfter(self.monitor_log_ctrl.AppendText, "スレッド終了\n")

    def _on_monitor_stop(self, event):
        self.monitor_monitoring = False
        self.monitor_timer.Stop()
        self.monitor_start_btn.Enable(True)
        self.monitor_stop_btn.Enable(False)
        self.monitor_log_ctrl.AppendText("監視停止\n")
        if _HAVE_MATPLOTLIB:
            is_depth_mode = self.monitor_mode_choice.GetSelection() == 1
            if is_depth_mode:
                self._update_depth_graph()
            else:
                self._update_monitor_graph()

    def _on_monitor_timer(self, event):
        now = time.perf_counter()
        t = now - self.monitor_t0
        duration_s = float(self.monitor_duration_ctrl.GetValue())
        if t > duration_s:
            self._on_monitor_stop(None)
            return
        
        # Collect data
        sys_cpu = psutil.cpu_percent(None)
        sys_mem = psutil.virtual_memory().percent
        
        proc_cpu = None
        proc_rss_mb = None
        if self.monitor_proc:
            try:
                proc_cpu = self.monitor_proc.cpu_percent(None)
                proc_rss_mb = self.monitor_proc.memory_info().rss / (1024 * 1024)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                self.monitor_proc = None
        
        gpu = _read_gpu() if self.monitor_have_nvml else {"gpu_util_avg": None, "gpu_mem_used_mib": None}
        
        self.monitor_rows.append({
            "t_sec": round(t, 3),
            "proc_cpu_percent": None if proc_cpu is None else round(proc_cpu, 2),
            "proc_rss_mb": None if proc_rss_mb is None else round(proc_rss_mb, 3),
            "sys_cpu_percent": round(sys_cpu, 2),
            "sys_mem_percent": round(sys_mem, 2),
            "gpu_util_avg": None if gpu["gpu_util_avg"] is None else round(gpu["gpu_util_avg"], 2),
            "gpu_mem_used_mib": None if gpu["gpu_mem_used_mib"] is None else round(gpu["gpu_mem_used_mib"], 2),
        })
        
        if _HAVE_MATPLOTLIB:
            self._update_monitor_graph()

    def _update_monitor_graph(self):
        if not self.monitor_rows or not _HAVE_MATPLOTLIB:
            return
        x = [r["t_sec"] for r in self.monitor_rows]
        
        # Process CPU
        y = [r["proc_cpu_percent"] for r in self.monitor_rows if r["proc_cpu_percent"] is not None]
        x_p = [r["t_sec"] for r in self.monitor_rows if r["proc_cpu_percent"] is not None]
        self.monitor_ax1.clear()
        if y:
            self.monitor_ax1.plot(x_p, y)
            self.monitor_ax1.set_title(f"Process CPU% (最大: {psutil.cpu_count()}コア × 100%)")
            max_cpu = max(y) if y else 100
            self.monitor_ax1.set_ylim(0, max(max_cpu * 1.1, 100))
        
        # System CPU
        self.monitor_ax2.clear()
        self.monitor_ax2.plot(x, [r["sys_cpu_percent"] for r in self.monitor_rows])
        self.monitor_ax2.set_title("System CPU%")
        self.monitor_ax2.set_ylim(0, 100)
        
        # Memory
        self.monitor_ax3.clear()
        self.monitor_ax3.plot(x, [r["sys_mem_percent"] for r in self.monitor_rows], label="Sys Mem%")
        y_mem = [r["proc_rss_mb"] for r in self.monitor_rows if r["proc_rss_mb"] is not None]
        x_mem = [r["t_sec"] for r in self.monitor_rows if r["proc_rss_mb"] is not None]
        if y_mem:
            self.monitor_ax3.plot(x_mem, y_mem, label="Proc RSS (MiB)")
        self.monitor_ax3.legend()
        self.monitor_ax3.set_title("メモリ")
        
        # GPU
        self.monitor_ax4.clear()
        if self.monitor_have_nvml:
            y_gpu = [r["gpu_util_avg"] for r in self.monitor_rows if r["gpu_util_avg"] is not None]
            x_gpu = [r["t_sec"] for r in self.monitor_rows if r["gpu_util_avg"] is not None]
            if y_gpu:
                self.monitor_ax4.plot(x_gpu, y_gpu, label="GPU Util%")
            y_mem_gpu = [r["gpu_mem_used_mib"] for r in self.monitor_rows if r["gpu_mem_used_mib"] is not None]
            x_mem_gpu = [r["t_sec"] for r in self.monitor_rows if r["gpu_mem_used_mib"] is not None]
            if y_mem_gpu:
                self.monitor_ax4.plot(x_mem_gpu, y_mem_gpu, label="GPU Mem (MiB)")
            self.monitor_ax4.legend()
            self.monitor_ax4.set_title("GPU")
        else:
            self.monitor_ax4.text(0.5, 0.5, "GPU利用不可", ha="center", va="center", transform=self.monitor_ax4.transAxes, fontname='MS Gothic', fontsize=12)
        
        self.monitor_figure.tight_layout()
        self.monitor_canvas.draw()

    def _calculate_equilibrium_point(self, depths, elapsed_avg, rss_avg, cpu_avg):
        """均衡点を計算する - CPU使用率、メモリ使用率、実行時間の和が最小となる点"""
        if not depths:
            return None

        # 各深さでの和を計算
        sums = [elapsed_avg[i] + rss_avg[i] + cpu_avg[i] for i in range(len(depths))]

        # 和が最小となるインデックスを見つける
        min_sum_index = sums.index(min(sums))

        return depths[min_sum_index]

    def _update_depth_graph(self):
        """深さベースのグラフを更新"""
        if not self.monitor_rows or not _HAVE_MATPLOTLIB:
            return
        
        # 深さごとに試行結果を集計
        depth_stats = {}
        for row in self.monitor_rows:
            d = row["depth"]
            if d not in depth_stats:
                depth_stats[d] = {
                    "elapsed": [],
                    "rss_delta": [],
                    "cpu": [],
                }
            depth_stats[d]["elapsed"].append(row["elapsed_sec"])
            depth_stats[d]["rss_delta"].append(row["rss_delta_mb"])
            depth_stats[d]["cpu"].append(row["cpu_percent"])
        
        if not depth_stats:
            return
        
        depths = sorted(depth_stats.keys())
        
        # グラフ更新
        # グラフ1: 実行時間
        self.monitor_ax1.clear()
        elapsed_avg = [sum(depth_stats[d]["elapsed"]) / len(depth_stats[d]["elapsed"]) for d in depths]
        elapsed_min = [min(depth_stats[d]["elapsed"]) for d in depths]
        elapsed_max = [max(depth_stats[d]["elapsed"]) for d in depths]
        self.monitor_ax1.plot(depths, elapsed_avg, marker='o', label="平均")
        self.monitor_ax1.fill_between(depths, elapsed_min, elapsed_max, alpha=0.3, label="範囲")
        self.monitor_ax1.set_xlabel("探索深さ")
        self.monitor_ax1.set_ylabel("実行時間 (秒)")
        self.monitor_ax1.set_title("実行時間 vs 探索深さ")
        self.monitor_ax1.legend()
        self.monitor_ax1.grid(True, alpha=0.3)
        
        # グラフ2: メモリ変化
        self.monitor_ax2.clear()
        rss_avg = [sum(depth_stats[d]["rss_delta"]) / len(depth_stats[d]["rss_delta"]) for d in depths]
        rss_min = [min(depth_stats[d]["rss_delta"]) for d in depths]
        rss_max = [max(depth_stats[d]["rss_delta"]) for d in depths]
        self.monitor_ax2.plot(depths, rss_avg, marker='s', color='green', label="平均")
        self.monitor_ax2.fill_between(depths, rss_min, rss_max, alpha=0.3, color='green', label="範囲")
        self.monitor_ax2.set_xlabel("探索深さ")
        self.monitor_ax2.set_ylabel("メモリ変化 (MB)")
        self.monitor_ax2.set_title("メモリ変化 vs 探索深さ")
        self.monitor_ax2.legend()
        self.monitor_ax2.grid(True, alpha=0.3)
        
        # グラフ3: CPU使用率
        self.monitor_ax3.clear()
        cpu_avg = [sum(depth_stats[d]["cpu"]) / len(depth_stats[d]["cpu"]) for d in depths]
        cpu_min = [min(depth_stats[d]["cpu"]) for d in depths]
        cpu_max = [max(depth_stats[d]["cpu"]) for d in depths]
        self.monitor_ax3.plot(depths, cpu_avg, marker='^', color='red', label="平均")
        self.monitor_ax3.fill_between(depths, cpu_min, cpu_max, alpha=0.3, color='red', label="範囲")
        self.monitor_ax3.set_xlabel("探索深さ")
        self.monitor_ax3.set_ylabel("CPU使用率 (%)")
        self.monitor_ax3.set_title(f"CPU使用率 vs 探索深さ (最大: {psutil.cpu_count()}コア × 100%)")
        max_cpu_val = max(cpu_max) if cpu_max else 100
        self.monitor_ax3.set_ylim(0, max(max_cpu_val * 1.1, 100))
        self.monitor_ax3.legend()
        self.monitor_ax3.grid(True, alpha=0.3)
        
        # 均衡点の計算
        equilibrium_depth = self._calculate_equilibrium_point(depths, elapsed_avg, rss_avg, cpu_avg)

        # グラフ4: 全体サマリー
        self.monitor_ax4.clear()
        self.monitor_ax4.axis('off')
        summary_text = "深さベース分析サマリー\n"
        summary_text += f"最小深さ: {depths[0]}\n"
        summary_text += f"最大深さ: {depths[-1]}\n"
        summary_text += f"総試行回数: {len(self.monitor_rows)}\n"
        summary_text += f"最大実行時間: {max(elapsed_avg):.2f}秒\n"
        summary_text += f"最大メモリ変化: {max(rss_avg):.2f}MB\n"
        if equilibrium_depth is not None:
            summary_text += f"均衡点 (深さ): {equilibrium_depth}\n"
        else:
            summary_text += "均衡点: 未達\n"
        self.monitor_ax4.text(0.1, 0.9, summary_text, transform=self.monitor_ax4.transAxes,
                             fontsize=11, verticalalignment='top', family='monospace', fontname='MS Gothic')
        
        self.monitor_figure.tight_layout()
        self.monitor_canvas.draw()

    def _on_monitor_save(self, event):
        if not self.monitor_rows:
            wx.MessageBox("保存するデータがありません。", "エラー", wx.ICON_ERROR)
            return
        
        outdir = "monitor_out"
        os.makedirs(outdir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        is_depth_mode = self.monitor_mode_choice.GetSelection() == 1
        
        if is_depth_mode:
            csv_path = os.path.join(outdir, f"depth_analysis_{stamp}.csv")
            fieldnames = ["depth", "trial", "elapsed_sec", "rss_mb", "rss_delta_mb", "cpu_percent"]
        else:
            csv_path = os.path.join(outdir, f"monitor_{stamp}.csv")
            fieldnames = [
                "t_sec", "proc_cpu_percent", "proc_rss_mb", "sys_cpu_percent", "sys_mem_percent",
                "gpu_util_avg", "gpu_mem_used_mib"
            ]
        
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(self.monitor_rows)
        
        self.monitor_log_ctrl.AppendText(f"CSV保存: {csv_path}\n")
        
        if _HAVE_MATPLOTLIB:
            png_path = os.path.join(outdir, f"graphs_{stamp}.png")
            self.monitor_figure.savefig(png_path, dpi=100, bbox_inches='tight')
            self.monitor_log_ctrl.AppendText(f"PNG保存: {png_path}\n")

    def on_new_game(self, event):
        dlg = wx.MessageDialog(
            self,
            "新しいゲームを開始しますか？",
            "確認",
            wx.YES_NO | wx.ICON_QUESTION
        )
        if dlg.ShowModal() == wx.ID_YES:
            self.board = chess.Board()
            self.move_stack = []
            self.uci_history = []
            self.board_panel.board = self.board
            self.board_panel.Refresh()
            self._update_game_info()
        dlg.Destroy()
    
    def _on_match_start(self, event):
        """対戦開始"""
        if self.match_running:
            wx.MessageBox("既に対戦が実行中です。", "エラー", wx.ICON_ERROR)
            return
        
        num_games = self.match_games_ctrl.GetValue()
        stockfish_path = self.match_sf_path_ctrl.GetValue()
        
        # Stockfishの接続確認
        actual_path = self._find_and_verify_stockfish(stockfish_path)
        if actual_path is None:
            return
        
        self.match_running = True
        self.match_start_btn.Enable(False)
        self.match_stop_btn.Enable(True)
        self.match_games_ctrl.Enable(False)  # ゲーム数は固定
        self.match_sf_path_ctrl.Enable(False)  # パスは固定
        # 深さコントロールは有効なまま（対戦中に変更可能）
        
        self.match_log_ctrl.AppendText(f"\n=== 対戦開始 ===\n")
        self.match_log_ctrl.AppendText(f"ゲーム数: {num_games}\n")
        self.match_log_ctrl.AppendText("(対戦中も深さを変更できます)\n\n")
        
        # スレッドで対戦実行
        self.match_thread = threading.Thread(
            target=self._run_match_thread,
            args=(num_games, actual_path),
            daemon=True
        )
        self.match_thread.start()
    
    def _run_match_thread(self, num_games, stockfish_path):
        """対戦実行スレッド"""
        try:
            results = {
                'total_games': num_games,
                'meraki_wins': 0,
                'stockfish_wins': 0,
                'draws': 0,
                'errors': 0,
                'games': []
            }
            
            for game_num in range(1, num_games + 1):
                if not self.match_running:
                    wx.CallAfter(self.match_log_ctrl.AppendText, f"\n対戦中止\n")
                    break
                
                # 現在の深さ設定を読み込む
                meraki_depth = self.match_meraki_depth_ctrl.GetValue()
                stockfish_depth = self.match_sf_depth_ctrl.GetValue()
                
                wx.CallAfter(
                    self.match_log_ctrl.AppendText,
                    f"ゲーム {game_num}/{num_games} 開始 "
                    f"(Meraki深さ: {meraki_depth}, Stockfish深さ: {stockfish_depth})\n"
                )
                
                try:
                    self.match = EngineMatch(
                        engine_path=stockfish_path,
                        meraki_depth=meraki_depth,
                        meraki_time_ms=1500,
                        stockfish_depth=stockfish_depth,
                        stockfish_time_ms=1000,
                        stockfish_skill_level=self.match_sf_skill_ctrl.GetValue(),
                            opening_book=DEFAULT_OPENING_BOOK,
                    )
                    
                    game_results = self.match.play_matches(num_matches=1)
                    game_info = game_results['games'][0]
                    
                    # 結果を統一形式に変換
                    raw_result = game_info['result']
                    if raw_result == "1-0":
                        # 白（1）が勝利
                        result_str = 'meraki_win' if game_info['meraki_white'] else 'stockfish_win'
                    elif raw_result == "0-1":
                        # 黒（0）が勝利
                        result_str = 'stockfish_win' if game_info['meraki_white'] else 'meraki_win'
                    elif raw_result == "1/2-1/2":
                        result_str = 'draw'
                    else:
                        result_str = 'error'
                    
                    game_info['result'] = result_str
                    
                    # 結果を集計
                    results['games'].append(game_info)
                    if game_info['result'] == 'meraki_win':
                        results['meraki_wins'] += 1
                    elif game_info['result'] == 'stockfish_win':
                        results['stockfish_wins'] += 1
                    elif game_info['result'] == 'draw':
                        results['draws'] += 1
                    else:
                        results['errors'] += 1
                    
                    meraki_color = "白" if game_info['meraki_white'] else "黒"
                    wx.CallAfter(
                        self.match_log_ctrl.AppendText,
                        f"  結果: {game_info['result']}, Meraki色: {meraki_color}, "
                        f"手数: {game_info['moves']}, 時間: {game_info['time_sec']:.1f}秒\n"
                    )
                    
                    if self.match:
                        self.match.close()
                        self.match = None
                    
                except Exception as e:
                    wx.CallAfter(
                        self.match_log_ctrl.AppendText,
                        f"  ゲーム {game_num} エラー: {str(e)}\n"
                    )
                    if self.match:
                        self.match.close()
                        self.match = None
            
            # 統計計算
            stats = self._calculate_stats(results)
            wx.CallAfter(self._update_match_results, results, stats)
            
        except Exception as e:
            wx.CallAfter(self.match_log_ctrl.AppendText, f"スレッドエラー: {str(e)}\n")
        finally:
            self.match_running = False
            wx.CallAfter(self.match_start_btn.Enable, True)
            wx.CallAfter(self.match_stop_btn.Enable, False)
            wx.CallAfter(self.match_games_ctrl.Enable, True)
            wx.CallAfter(self.match_sf_path_ctrl.Enable, True)
            wx.CallAfter(self.match_log_ctrl.AppendText, "対戦終了\n")
    
    def _calculate_stats(self, results):
        """対戦結果から統計情報を計算"""
        total = results['total_games']
        meraki_wins = results['meraki_wins']
        draws = results['draws']
        
        meraki_score = meraki_wins + draws * 0.5
        meraki_win_rate = (meraki_score / total * 100) if total > 0 else 0
        
        game_lengths = [g['moves'] for g in results['games']]
        avg_game_length = sum(game_lengths) / len(game_lengths) if game_lengths else 0
        
        game_times = [g['time_sec'] for g in results['games']]
        avg_game_time_sec = sum(game_times) / len(game_times) if game_times else 0
        
        # 簡易的なELO差推定
        meraki_win_rate_decimal = meraki_win_rate / 100
        if 0 < meraki_win_rate_decimal < 1:
            estimated_elo_diff = int(400 * (2 * meraki_win_rate_decimal - 1) / (2 * meraki_win_rate_decimal * (1 - meraki_win_rate_decimal)))
        elif meraki_win_rate_decimal == 1:
            estimated_elo_diff = 400
        elif meraki_win_rate_decimal == 0:
            estimated_elo_diff = -400
        else:
            estimated_elo_diff = 0
        
        return {
            'meraki_win_rate': meraki_win_rate,
            'meraki_score': meraki_score,
            'avg_game_length': avg_game_length,
            'avg_game_time_sec': avg_game_time_sec,
            'estimated_elo_diff': estimated_elo_diff,
        }
    
    def _update_match_results(self, results, stats):
        """対戦結果を画面に表示"""
        self.match_log_ctrl.AppendText(f"\n=== 対戦完了 ===\n")
        self.match_log_ctrl.AppendText(f"総ゲーム数: {results['total_games']}\n")
        
        error_count = results.get('errors', 0)
        error_line = f"エラー数: {error_count}\n" if error_count > 0 else ""
        result_text = f"""=== 統計情報 ===
総ゲーム数: {results['total_games']}
Meraki勝利: {results['meraki_wins']}
Stockfish勝利: {results['stockfish_wins']}
引き分け: {results['draws']}
{error_line}
=== 詳細統計 ===
勝率: {stats['meraki_win_rate']:.1f}%
スコア: {stats['meraki_score']:.1f}/{results['total_games']}
平均ゲーム長: {stats['avg_game_length']:.1f} 手
平均ゲーム時間: {stats['avg_game_time_sec']:.2f} 秒
推定ELO差: {stats['estimated_elo_diff']}
"""
        self.match_result_ctrl.SetValue(result_text)
        
        # 統計タブは新しい結果で置き換え（上書き）
        self.stats_ctrl.SetValue(result_text)
        
        # 結果を保存して保存ボタンを有効にする
        self.match_last_results = {
            'results': results,
            'stats': stats,
            'timestamp': datetime.now()
        }
        self.match_save_btn.Enable(True)
        
        # ゲーム選択ドロップダウンを更新
        self._update_game_choice_dropdown(results)
    
    def _on_match_stop(self, event):
        """対戦中止"""
        if self.match_running:
            self.match_log_ctrl.AppendText("\n対戦を中止します...\n")
            self.match_running = False
    
    def _update_game_choice_dropdown(self, results):
        """ゲーム選択ドロップダウンを更新"""
        self.replay_game_choice.Clear()
        for i, game in enumerate(results['games'], 1):
            result_str = game['result'].replace('_', ' ')
            label = f"ゲーム {i}: {result_str} ({game['moves']}手)"
            self.replay_game_choice.Append(label)
        
        # 最初のゲームを選択
        if results['games']:
            self.replay_game_choice.SetSelection(0)
    
    def _on_match_save(self, event):
        """対戦結果をCSVに保存"""
        if self.match_last_results is None:
            wx.MessageBox("保存する対戦結果がありません。", "エラー", wx.ICON_ERROR)
            return
        
        outdir = "match_results"
        os.makedirs(outdir, exist_ok=True)
        csv_path = os.path.join(outdir, "match_history.csv")
        
        results = self.match_last_results['results']
        stats = self.match_last_results['stats']
        timestamp = self.match_last_results['timestamp']
        
        # 全ゲームのデータを整形
        rows = []
        for game_idx, game in enumerate(results['games'], 1):
            row = {
                'timestamp': timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                'game_num': game_idx,
                'total_games': results['total_games'],
                'result': game['result'],
                'meraki_white': 'Yes' if game['meraki_white'] else 'No',
                'moves': game['moves'],
                'time_sec': round(game['time_sec'], 2),
            }
            rows.append(row)
        
        # 統計行を最後に追加
        stats_row = {
            'timestamp': timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            'game_num': '[統計]',
            'total_games': results['total_games'],
            'result': f"勝率: {stats['meraki_win_rate']:.1f}%",
            'meraki_white': f"Win: {results['meraki_wins']}",
            'moves': f"Loss: {results['stockfish_wins']}",
            'time_sec': f"Draw: {results['draws']}",
        }
        rows.append(stats_row)
        
        # CSVに追記
        file_exists = os.path.isfile(csv_path)
        
        fieldnames = ['timestamp', 'game_num', 'total_games', 'result', 'meraki_white', 'moves', 'time_sec']
        
        with open(csv_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            
            # ファイルが存在しない場合、ヘッダーを書き込み
            if not file_exists:
                writer.writeheader()
            
            # データを追記
            writer.writerows(rows)
        
        success_msg = f"""対戦結果を保存しました：

ファイル: {csv_path}

保存内容:
- {len(results['games'])} ゲーム分のゲーム詳細
- 統計情報（勝率、ELO差など）

※ 複数回実行すると、前回の結果の下に追記されます"""
        
        self.match_log_ctrl.AppendText(f"\n✓ CSV保存完了: {csv_path}\n")
        wx.MessageBox(success_msg, "保存完了", wx.ICON_INFORMATION)
    
    def _on_replay_game(self, event):
        """ゲーム再生開始"""
        if self.match_last_results is None or not self.match_last_results['results']['games']:
            wx.MessageBox("再生するゲームがありません。", "エラー", wx.ICON_ERROR)
            return
        
        sel = self.replay_game_choice.GetSelection()
        if sel == wx.NOT_FOUND:
            wx.MessageBox("ゲームを選択してください。", "エラー", wx.ICON_ERROR)
            return
        
        game_info = self.match_last_results['results']['games'][sel]
        
        # UIを初期化
        self.replay_board = chess.Board()
        
        # 手順データを取得（複数の形式に対応）
        self.replay_moves = game_info.get('moves_uci', [])
        if not self.replay_moves and 'pgn' in game_info:
            # PGNから手順を復元
            try:
                game = chess.pgn.read_game(io.StringIO(game_info['pgn']))
                self.replay_moves = [move.uci() for move in game.mainline_moves()]
            except:
                self.replay_moves = []
        
        self.replay_current_move = 0
        
        if not self.replay_moves:
            wx.MessageBox("この対戦にはムーブデータがありません。\n別の対戦を試してください。", "情報", wx.ICON_INFORMATION)
            return
        
        # ゲーム情報を保存（結果確認用）
        self.replay_game_info = game_info
        
        # ボタンを有効化
        self.replay_prev_btn.Enable(True)
        self.replay_back_btn.Enable(True)
        self.replay_forward_btn.Enable(True)
        self.replay_last_btn.Enable(True)
        
        # 初期状態で表示
        self._update_replay_display()
    
    def _on_replay_prev(self, event):
        """再生を最初に戻す"""
        self.replay_current_move = 0
        self._update_replay_display()
    
    def _on_replay_back(self, event):
        """1手戻す"""
        if self.replay_current_move > 0:
            self.replay_current_move -= 1
        self._update_replay_display()
    
    def _on_replay_forward(self, event):
        """1手進める"""
        if self.replay_current_move < len(self.replay_moves):
            self.replay_current_move += 1
        self._update_replay_display()
    
    def _on_replay_last(self, event):
        """再生を最後に"""
        self.replay_current_move = len(self.replay_moves)
        self._update_replay_display()
    
    def _update_replay_display(self):
        """再生画面を更新"""
        if self.replay_board is None:
            return
        
        # ボードをリセット
        self.replay_board = chess.Board()
        
        # 現在の手数まで進める
        for i in range(self.replay_current_move):
            if i < len(self.replay_moves):
                try:
                    move = chess.Move.from_uci(self.replay_moves[i])
                    self.replay_board.push(move)
                except:
                    break
        
        # 手数表示を更新
        self.replay_move_num.SetLabel(f"手数: {self.replay_current_move}/{len(self.replay_moves)}")
        
        # ボード描画
        self._draw_replay_board()
        
        # PGN表示
        pgn_text = self._generate_pgn_display()
        
        # ゲーム情報を表示
        if hasattr(self, 'replay_game_info'):
            game_info = self.replay_game_info
            result = game_info.get('result', '不明')
            meraki_color = "白" if game_info.get('meraki_white', True) else "黒"
            stockfish_color = "黒" if game_info.get('meraki_white', True) else "白"
            
            # 結果を日本語で表示
            if result == 'meraki_win':
                result_text = f"✓ Meraki({meraki_color})の勝利！"
            elif result == 'stockfish_win':
                result_text = f"✗ Meraki({meraki_color})の敗北（Stockfish({stockfish_color})の勝利）"
            else:
                result_text = "= 引き分け"
            
            game_info_text = f"{result_text}\n\n{pgn_text}"
        else:
            game_info_text = pgn_text
        
        self.replay_pgn_ctrl.SetValue(game_info_text)
    
    def _draw_replay_board(self):
        """再生用ボードを描画"""
        dc = wx.ClientDC(self.replay_board_panel)
        dc.SetBrush(wx.Brush(wx.Colour(50, 50, 50)))
        dc.DrawRectangle(0, 0, SQUARE_SIZE * 8, SQUARE_SIZE * 8)
        
        for rank in range(8):
            for file in range(8):
                # ボード座標は白が下になる通常の向きにする
                sq = chess.square(file, 7 - rank)

                # 色（白マス/黒マスの通常割り当て）
                is_light = (file + rank) % 2 == 0
                color = LIGHT_COLOR if is_light else DARK_COLOR
                
                # 最後の手のハイライト
                if self.replay_current_move > 0 and self.replay_current_move <= len(self.replay_moves):
                    last_move = chess.Move.from_uci(self.replay_moves[self.replay_current_move - 1])
                    if sq in [last_move.from_square, last_move.to_square]:
                        color = HIGHLIGHT_COLOR
                
                dc.SetBrush(wx.Brush(color))
                dc.SetPen(wx.Pen(color))
                dc.DrawRectangle(file * SQUARE_SIZE, rank * SQUARE_SIZE,
                                SQUARE_SIZE, SQUARE_SIZE)
                
                # 駒の描画
                piece = self.replay_board.piece_at(sq)
                if piece:
                    label = piece.symbol()
                    dc.SetFont(wx.Font(28, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
                    dc.SetTextForeground(wx.BLACK if piece.color else wx.WHITE)
                    dc.DrawText(label,
                               file * SQUARE_SIZE + 16,
                               rank * SQUARE_SIZE + 16)
    
    def _generate_pgn_display(self) -> str:
        """PGN形式で棋譜を生成"""
        pgn_lines = []
        
        for i, uci in enumerate(self.replay_moves, 1):
            try:
                move = chess.Move.from_uci(uci)
                board_tmp = chess.Board()
                
                # i-1番目までの手を指す
                for j in range(i - 1):
                    board_tmp.push(chess.Move.from_uci(self.replay_moves[j]))
                
                # 移動前の局面でSAN記法に変換
                san = board_tmp.san(move)
                
                # 手数表記
                if (i - 1) % 2 == 0:  # 白の手
                    if (i - 1) % 4 == 0:
                        pgn_lines.append(f"{(i + 1) // 2}. {san}")
                    else:
                        pgn_lines[-1] += f" {san}"
                else:  # 黒の手
                    pgn_lines[-1] += f" {san}"
            except:
                pass
        
        pgn_text = " ".join(pgn_lines)
        
        # 現在の手を明示
        if 0 < self.replay_current_move <= len(self.replay_moves):
            try:
                move = chess.Move.from_uci(self.replay_moves[self.replay_current_move - 1])
                board_tmp = chess.Board()
                for j in range(self.replay_current_move - 1):
                    board_tmp.push(chess.Move.from_uci(self.replay_moves[j]))
                san = board_tmp.san(move)
                pgn_text = pgn_text.replace(san, f"→ {san} ←", 1)
            except:
                pass
        
        return pgn_text
    
    def _update_match_results_with_moves(self, results, stats):
        """対戦結果をゲーム選択ドロップダウンに反映"""
        self.match_last_results = {
            'results': results,
            'stats': stats,
            'timestamp': datetime.now()
        }
        
        # ゲーム選択ドロップダウンを更新
        self.replay_game_choice.Clear()
        for i, game in enumerate(results['games'], 1):
            result_str = game['result'].replace('_', ' ')
            label = f"ゲーム {i}: {result_str} ({game['moves']}手)"
            self.replay_game_choice.Append(label)
        
        # 最初のゲームを選択
        if results['games']:
            self.replay_game_choice.SetSelection(0)
    
    def _find_and_verify_stockfish(self, provided_path: str) -> Optional[str]:
        """
        Stockfishを探して接続確認する。
        複数の場所を試行し、最初に見つかったものを返す。
        """
        import shutil
        import os
        
        # 試行するパスのリスト
        paths_to_try = [
            provided_path,  # ユーザー指定のパス
            "stockfish",    # PATH環境変数
            "stockfish.exe",
            os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "Stockfish", "stockfish.exe"),
            os.path.join(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"), "Stockfish", "stockfish.exe"),
            os.path.join(os.path.expanduser("~"), "AppData", "Local", "Stockfish", "stockfish.exe"),
            os.path.join(os.path.expanduser("~"), "Stockfish", "stockfish.exe"),
        ]
        
        # 重複を除去
        paths_to_try = list(dict.fromkeys(paths_to_try))
        
        self.match_log_ctrl.AppendText("🔍 Stockfishを検索中...\n")
        
        for path in paths_to_try:
            try:
                # PATHから探す場合
                if path in ["stockfish", "stockfish.exe"]:
                    full_path = shutil.which(path)
                    if full_path is None:
                        continue
                    path = full_path
                
                # ファイルが存在するか確認
                if not os.path.isfile(path):
                    continue
                
                # 接続テスト
                try:
                    import chess.engine
                    test_engine = chess.engine.SimpleEngine.popen_uci(path)
                    test_engine.quit()
                    self.match_log_ctrl.AppendText(f"✓ Stockfish検出: {path}\n")
                    return path
                except Exception as e:
                    continue
            except Exception:
                continue
        
        # 全て失敗
        self.match_log_ctrl.AppendText("✗ Stockfishが見つかりません\n")
        error_msg = """Stockfishが見つかりません。以下のいずれかを実施してください：

【方法1】 Stockfishをインストール
- https://stockfishchess.org/download/ からダウンロード
- インストール後、自動検出されます

【方法2】 インストール済みの場合はパスを指定
1. Stockfishのインストール先を確認
2. 下記のように絶対パスを入力してください：
   例: C:\\Program Files\\Stockfish\\stockfish.exe
   
【方法3】 PATH環境変数に登録
- StockfishのあるフォルダをPATHに追加
"""
        wx.MessageBox(error_msg, "Stockfishが見つかりません", wx.ICON_ERROR)
        return None

    # ========== 人間の手を処理 ==========
    def push_move(self, move: chess.Move):
        # 待った用に現在局面のFENを保存
        self.move_stack.append(self.board.fen())

        # 実際に手を指す
        self.board.push(move)
        self.uci_history.append(move.uci())

        self.board_panel.Refresh()
        self._update_game_info()

        # 終局していなければ AI の手番へ
        if not self.board.is_game_over():
            wx.CallLater(50, self.ai_move)

    def _update_game_info(self):
        info = f"FEN: {self.board.fen()}\n"
        info += f"手数: {len(self.uci_history)}\n"
        if self.board.is_check():
            info += "状態: チェック\n"
        if self.board.is_game_over():
            info += f"終局: {self.board.result()}\n"
        self.game_info_ctrl.SetValue(info)


    # ========== AI の手 ==========
    def ai_move(self):
        if self.board.is_game_over():
            return

        # 現在のAI深さ設定を読み込む
        ai_depth = self.game_ai_depth_ctrl.GetValue()
        
        mv_uci = find_best_move(
            self.board,
            depth=ai_depth,
            time_ms=1500,
            coeff_path=None,
            ml_alpha=0.3,
            opening_book=DEFAULT_OPENING_BOOK,
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
        self._update_game_info()


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
        game.headers["Date"] = datetime.now().strftime("%Y.%m.%d")
        game.headers["White"] = "Human"
        game.headers["Black"] = "Meraki Engine"
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



# ==== ヘルパー関数 ====
def _init_process(pid: Optional[int]) -> Optional[psutil.Process]:
    if pid is None:
        p = psutil.Process()
    else:
        p = psutil.Process(pid)
    try:
        p.cpu_percent(None)
    except Exception:
        pass
    return p

def _init_nvml() -> bool:
    if not _HAVE_NVML:
        return False
    try:
        pynvml.nvmlInit()
        return True
    except Exception:
        return False

def _read_gpu() -> Dict[str, Any]:
    out = {"gpu_util_avg": None, "gpu_mem_used_mib": None}
    if not _HAVE_NVML:
        return out
    try:
        count = pynvml.nvmlDeviceGetCount()
        if count == 0:
            return out
        utils = []
        mems = []
        for i in range(count):
            h = pynvml.nvmlDeviceGetHandleByIndex(i)
            util = pynvml.nvmlDeviceGetUtilizationRates(h).gpu
            mem = pynvml.nvmlDeviceGetMemoryInfo(h).used / (1024 * 1024)
            utils.append(util)
            mems.append(mem)
        out["gpu_util_avg"] = sum(utils) / len(utils)
        out["gpu_mem_used_mib"] = sum(mems)
    except Exception:
        pass
    return out


# ==== 起動部分 ====
def main():
    app = wx.App(False)
    MainFrame()
    app.MainLoop()



if __name__ == "__main__":
    main()
