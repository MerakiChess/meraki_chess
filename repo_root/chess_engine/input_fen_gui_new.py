import wx

# --- Unicode chess symbols ---
UNICODE = {
    'K': '♔', 'Q': '♕', 'R': '♖', 'B': '♗', 'N': '♘', 'P': '♙',
    'k': '♚', 'q': '♛', 'r': '♜', 'b': '♝', 'n': '♞', 'p': '♟',
    '':  ''
}

FILES = "abcdefgh"
RANKS = "87654321"

LIGHT_COLOR = "#F0D9B5"
DARK_COLOR  = "#B58863"

class FenGUI(wx.Frame):
    def __init__(self, parent):
        super().__init__(parent, title="FEN Maker (pieces + history options)", size=(1000, 660))
        
        # ---- state ----
        self.selected_piece = 'P'
        self.board = [['' for _ in range(8)] for _ in range(8)]
        self.side_to_move = 'w'   # w/b
        self.castle_k = True      # K
        self.castle_q = True      # Q
        self.castle_kb = True     # k
        self.castle_qb = True     # q
        self.enpassant = '-'      # "-" or a3/e6
        self.halfmove = '0'       # >=0
        self.fullmove = '1'       # >=1

        self._build_ui()
        self._load_start_position()
        self._update_fen()

    # ---------- UI ----------
    def _build_ui(self):
        main_panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        # Left panel
        left_panel = wx.Panel(main_panel)
        left_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Palette
        left_sizer.Add(wx.StaticText(left_panel, label="Piece Palette"), 0, wx.ALL, 5)
        palette_sizer = wx.BoxSizer(wx.VERTICAL)
        row1_sizer = wx.BoxSizer(wx.HORIZONTAL)
        for p in ['K','Q','R','B','N','P']:
            self._make_palette_btn(left_panel, row1_sizer, p)
        palette_sizer.Add(row1_sizer, 0, wx.ALL, 5)
        row2_sizer = wx.BoxSizer(wx.HORIZONTAL)
        for p in ['k','q','r','b','n','p']:
            self._make_palette_btn(left_panel, row2_sizer, p)
        palette_sizer.Add(row2_sizer, 0, wx.ALL, 5)
        left_sizer.Add(palette_sizer, 0, wx.EXPAND)
        
        eraser_btn = wx.Button(left_panel, label="Eraser (空)", size=(100, -1))
        eraser_btn.Bind(wx.EVT_BUTTON, lambda evt: self._select_piece(''))
        left_sizer.Add(eraser_btn, 0, wx.ALL, 5)
        
        self.sel_lbl = wx.StaticText(left_panel, label="Selected: ♙ (P)")
        left_sizer.Add(self.sel_lbl, 0, wx.ALL, 5)
        
        # Convenience
        start_btn = wx.Button(left_panel, label="Start pos", size=(100, -1))
        start_btn.Bind(wx.EVT_BUTTON, self._load_start_position)
        left_sizer.Add(start_btn, 0, wx.ALL, 2)
        clear_btn = wx.Button(left_panel, label="Clear board", size=(100, -1))
        clear_btn.Bind(wx.EVT_BUTTON, self._clear_board)
        left_sizer.Add(clear_btn, 0, wx.ALL, 2)
        
        # FEN I/O
        fen_box = wx.StaticBoxSizer(wx.VERTICAL, left_panel, "FEN")
        self.fen_text = wx.TextCtrl(fen_box.GetStaticBox(), style=wx.TE_MULTILINE, size=(-1, 60))
        fen_box.Add(self.fen_text, 1, wx.EXPAND | wx.ALL, 5)
        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        copy_btn = wx.Button(fen_box.GetStaticBox(), label="Copy")
        copy_btn.Bind(wx.EVT_BUTTON, self._copy_fen)
        load_btn = wx.Button(fen_box.GetStaticBox(), label="Load FEN")
        load_btn.Bind(wx.EVT_BUTTON, self._load_fen_from_text)
        btn_row.Add(load_btn, 0, wx.ALL, 5)
        btn_row.Add(copy_btn, 0, wx.ALL, 5)
        fen_box.Add(btn_row, 0, wx.ALIGN_RIGHT)
        left_sizer.Add(fen_box, 0, wx.EXPAND | wx.ALL, 5)
        
        left_panel.SetSizer(left_sizer)
        main_sizer.Add(left_panel, 0, wx.EXPAND | wx.ALL, 10)
        
        # Center: Board
        center_panel = wx.Panel(main_panel)
        center_sizer = wx.BoxSizer(wx.VERTICAL)
        board_frame = wx.Panel(center_panel, style=wx.SIMPLE_BORDER)
        board_sizer = wx.GridSizer(8, 8, 0, 0)
        self.sq_buttons = []
        for y in range(8):
            row_buttons = []
            for x in range(8):
                bg = LIGHT_COLOR if (x + y) % 2 == 0 else DARK_COLOR
                btn = wx.Button(board_frame, label='', size=(50, 50))
                btn.SetFont(wx.Font(20, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
                btn.SetBackgroundColour(bg)
                btn.Bind(wx.EVT_BUTTON, lambda evt, yy=y, xx=x: self._place_on_square(yy, xx))
                btn.Bind(wx.EVT_RIGHT_DOWN, lambda evt, yy=y, xx=x: self._erase_square(yy, xx))
                board_sizer.Add(btn, 0, wx.EXPAND)
                row_buttons.append(btn)
            self.sq_buttons.append(row_buttons)
        board_frame.SetSizer(board_sizer)
        center_sizer.Add(board_frame, 0, wx.ALL, 5)
        center_sizer.Add(wx.StaticText(center_panel, label="左クリック: 置く／差し替え   右クリック: 消す"), 0, wx.ALL, 5)
        center_panel.SetSizer(center_sizer)
        main_sizer.Add(center_panel, 0, wx.EXPAND | wx.ALL, 10)
        
        # Right: History Options
        right_panel = wx.Panel(main_panel)
        right_sizer = wx.BoxSizer(wx.VERTICAL)
        right_sizer.Add(wx.StaticText(right_panel, label="History options"), 0, wx.ALL, 5)
        
        # Side to move
        stm_box = wx.StaticBoxSizer(wx.VERTICAL, right_panel, "Side to move")
        self.rb_white = wx.RadioButton(stm_box.GetStaticBox(), label="White (w)", style=wx.RB_GROUP)
        self.rb_black = wx.RadioButton(stm_box.GetStaticBox(), label="Black (b)")
        self.rb_white.Bind(wx.EVT_RADIOBUTTON, lambda evt: self._on_side_change('w'))
        self.rb_black.Bind(wx.EVT_RADIOBUTTON, lambda evt: self._on_side_change('b'))
        stm_box.Add(self.rb_white, 0, wx.ALL, 2)
        stm_box.Add(self.rb_black, 0, wx.ALL, 2)
        right_sizer.Add(stm_box, 0, wx.EXPAND | wx.ALL, 5)
        
        # Castling rights
        cas_box = wx.StaticBoxSizer(wx.VERTICAL, right_panel, "Castling rights (資格の有無)")
        self.cb_k = wx.CheckBox(cas_box.GetStaticBox(), label="K  (White short)")
        self.cb_q = wx.CheckBox(cas_box.GetStaticBox(), label="Q  (White long)")
        self.cb_kb = wx.CheckBox(cas_box.GetStaticBox(), label="k  (Black short)")
        self.cb_qb = wx.CheckBox(cas_box.GetStaticBox(), label="q  (Black long)")
        self.cb_k.SetValue(True)
        self.cb_q.SetValue(True)
        self.cb_kb.SetValue(True)
        self.cb_qb.SetValue(True)
        self.cb_k.Bind(wx.EVT_CHECKBOX, lambda evt: self._on_castle_change())
        self.cb_q.Bind(wx.EVT_CHECKBOX, lambda evt: self._on_castle_change())
        self.cb_kb.Bind(wx.EVT_CHECKBOX, lambda evt: self._on_castle_change())
        self.cb_qb.Bind(wx.EVT_CHECKBOX, lambda evt: self._on_castle_change())
        cas_box.Add(self.cb_k, 0, wx.ALL, 2)
        cas_box.Add(self.cb_q, 0, wx.ALL, 2)
        cas_box.Add(self.cb_kb, 0, wx.ALL, 2)
        cas_box.Add(self.cb_qb, 0, wx.ALL, 2)
        suggest_btn = wx.Button(cas_box.GetStaticBox(), label="Suggest castling (盤面から推定)")
        suggest_btn.Bind(wx.EVT_BUTTON, self._suggest_castling)
        cas_box.Add(suggest_btn, 0, wx.ALL, 5)
        right_sizer.Add(cas_box, 0, wx.EXPAND | wx.ALL, 5)
        
        # En passant
        ep_box = wx.StaticBoxSizer(wx.VERTICAL, right_panel, "En passant target")
        ep_box.Add(wx.StaticText(ep_box.GetStaticBox(), label="Square (- / a3..h3 / a6..h6)"), 0, wx.ALL, 2)
        self.ep_ctrl = wx.TextCtrl(ep_box.GetStaticBox(), value='-')
        self.ep_ctrl.Bind(wx.EVT_TEXT, lambda evt: self._on_ep_change())
        ep_box.Add(self.ep_ctrl, 0, wx.EXPAND | wx.ALL, 2)
        right_sizer.Add(ep_box, 0, wx.EXPAND | wx.ALL, 5)
        
        # Clocks
        clk_box = wx.StaticBoxSizer(wx.VERTICAL, right_panel, "Clocks")
        rowc_sizer = wx.BoxSizer(wx.HORIZONTAL)
        rowc_sizer.Add(wx.StaticText(clk_box.GetStaticBox(), label="Halfmove (>=0):"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 2)
        self.half_ctrl = wx.TextCtrl(clk_box.GetStaticBox(), value='0', size=(50, -1))
        self.half_ctrl.Bind(wx.EVT_TEXT, lambda evt: self._on_half_change())
        rowc_sizer.Add(self.half_ctrl, 0, wx.ALL, 2)
        rowc_sizer.Add(wx.StaticText(clk_box.GetStaticBox(), label="Fullmove (>=1):"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 2)
        self.full_ctrl = wx.TextCtrl(clk_box.GetStaticBox(), value='1', size=(50, -1))
        self.full_ctrl.Bind(wx.EVT_TEXT, lambda evt: self._on_full_change())
        rowc_sizer.Add(self.full_ctrl, 0, wx.ALL, 2)
        clk_box.Add(rowc_sizer, 0, wx.EXPAND)
        right_sizer.Add(clk_box, 0, wx.EXPAND | wx.ALL, 5)
        
        right_sizer.Add(wx.StaticText(right_panel, label="※ キャスリング権は“可能性”ではなく“資格”。\n※ EPは直前手で2歩前進があり、かつ捕獲可能な時のみ。"), 0, wx.ALL, 5)
        
        right_panel.SetSizer(right_sizer)
        main_sizer.Add(right_panel, 0, wx.EXPAND | wx.ALL, 10)
        
        main_panel.SetSizer(main_sizer)

    def _make_palette_btn(self, parent, sizer, piece_code):
        btn = wx.Button(parent, label=UNICODE[piece_code], size=(40, 40))
        btn.SetFont(wx.Font(16, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        btn.Bind(wx.EVT_BUTTON, lambda evt, p=piece_code: self._select_piece(p))
        sizer.Add(btn, 0, wx.ALL, 2)

    def _select_piece(self, p):
        self.selected_piece = p
        sym = UNICODE[p] if p else '∅'
        tag = p.upper() if p else 'empty'
        self.sel_lbl.SetLabel(f"Selected: {sym} ({tag})")

    # ---------- Board ops ----------
    def _place_on_square(self, y, x):
        self.board[y][x] = self.selected_piece
        self._render_square(y, x)
        self._update_fen()

    def _erase_square(self, y, x):
        self.board[y][x] = ''
        self._render_square(y, x)
        self._update_fen()

    def _render_square(self, y, x):
        self.sq_buttons[y][x].SetLabel(UNICODE[self.board[y][x]])

    def _render_all(self):
        for y in range(8):
            for x in range(8):
                self._render_square(y, x)

    # ---------- FEN helpers ----------
    def _board_to_fen_placement(self):
        ranks = []
        for y in range(8):
            empties = 0
            parts = []
            for x in range(8):
                p = self.board[y][x]
                if p == '':
                    empties += 1
                else:
                    if empties:
                        parts.append(str(empties))
                        empties = 0
                    parts.append(p)
            if empties:
                parts.append(str(empties))
            ranks.append(''.join(parts))
        return '/'.join(ranks)

    def _valid_ep(self, s):
        if s == '-': return True
        if len(s) != 2: return False
        f, r = s[0], s[1]
        return (f in FILES) and (r in "36")

    def _castling_rights_str(self):
        out = ''
        if self.castle_k: out += 'K'
        if self.castle_q: out += 'Q'
        if self.castle_kb: out += 'k'
        if self.castle_qb: out += 'q'
        return out if out else '-'

    def _suggest_castling(self, event=None):
        def piece_at(sq):
            f = FILES.index(sq[0]); r = RANKS.index(sq[1])
            return self.board[r][f]
        def empty(sqs):
            for sq in sqs:
                f = FILES.index(sq[0]); r = RANKS.index(sq[1])
                if self.board[r][f] != '':
                    return False
            return True

        k = q = kb = qb = False

        if piece_at('e1') == 'K':
            if piece_at('h1') == 'R' and empty(['f1','g1']): k = True
            if piece_at('a1') == 'R' and empty(['b1','c1','d1']): q = True
        if piece_at('e8') == 'k':
            if piece_at('h8') == 'r' and empty(['f8','g8']): kb = True
            if piece_at('a8') == 'r' and empty(['b8','c8','d8']): qb = True

        self.castle_k = k; self.castle_q = q
        self.castle_kb = kb; self.castle_qb = qb
        self._update_fen()

    def _current_fen(self):
        placement = self._board_to_fen_placement()
        stm = self.side_to_move
        cast = self._castling_rights_str()
        ep = self.enpassant.strip()
        ep = ep if self._valid_ep(ep) else '-'
        hm = self.halfmove.strip()
        fm = self.fullmove.strip()
        hm = hm if hm.isdigit() and int(hm) >= 0 else '0'
        fm = fm if fm.isdigit() and int(fm) >= 1 else '1'
        return f"{placement} {stm} {cast} {ep} {hm} {fm}"

    def _update_fen(self):
        fen = self._current_fen()
        self.fen_text.SetValue(fen)

    def _clear_board(self, event=None):
        self.board = [['' for _ in range(8)] for _ in range(8)]
        self.side_to_move = 'w'
        self.castle_k = False; self.castle_q = False
        self.castle_kb = False; self.castle_qb = False
        self.enpassant = '-'; self.halfmove = '0'; self.fullmove = '1'
        self._render_all(); self._update_fen()

    def _load_start_position(self, event=None):
        start = [
            list("rnbqkbnr"),
            list("pppppppp"),
            ['']*8, ['']*8, ['']*8, ['']*8,
            list("PPPPPPPP"),
            list("RNBQKBNR"),
        ]
        self.board = start
        self.side_to_move = 'w'
        self.castle_k = True; self.castle_q = True
        self.castle_kb = True; self.castle_qb = True
        self.enpassant = '-'; self.halfmove = '0'; self.fullmove = '1'
        self._render_all(); self._update_fen()

    def _copy_fen(self, event=None):
        fen = self.fen_text.GetValue().strip()
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(fen))
            wx.TheClipboard.Close()
            wx.MessageBox("FENをクリップボードにコピーしました。", "Copied")

    def _load_fen_from_text(self, event=None):
        fen = self.fen_text.GetValue().strip()
        try:
            self._load_fen(fen)
            self._render_all()
            self._update_fen()
        except Exception as e:
            wx.MessageBox(f"不正なFENです。\n{e}", "FEN読み込みエラー", wx.ICON_ERROR)

    def _load_fen(self, fen):
        parts = fen.split()
        if len(parts) != 6:
            raise ValueError("FENは6フィールド必要です。")
        placement, stm, cast, ep, hm, fm = parts

        ranks = placement.split('/')
        if len(ranks) != 8:
            raise ValueError("盤面のランク数が8ではありません。")
        new_board = []
        for r in ranks:
            row, count = [], 0
            for ch in r:
                if ch.isdigit():
                    row += [''] * int(ch); count += int(ch)
                elif ch in "prnbqkPRNBQK":
                    row.append(ch); count += 1
                else:
                    raise ValueError(f"未知の盤面文字: {ch}")
            if count != 8:
                raise ValueError("各ランクは8マスでなければなりません。")
            new_board.append(row)
        self.board = new_board

        if stm not in ('w','b'):
            raise ValueError("手番は w または b。")
        self.side_to_move = stm

        self.castle_k = 'K' in cast
        self.castle_q = 'Q' in cast
        self.castle_kb = 'k' in cast
        self.castle_qb = 'q' in cast
        if cast == '-':
            self.castle_k = False; self.castle_q = False
            self.castle_kb = False; self.castle_qb = False

        if not self._valid_ep(ep):
            raise ValueError("en passant は '-' か rank 3/6 のマス名を入力。")
        self.enpassant = ep

        if not hm.isdigit() or int(hm) < 0:
            raise ValueError("halfmove は0以上の整数。")
        if not fm.isdigit() or int(fm) < 1:
            raise ValueError("fullmove は1以上の整数。")
        self.halfmove = hm; self.fullmove = fm

    # イベントハンドラー（追加）
    def _on_side_change(self, side):
        self.side_to_move = side
        self._update_fen()

    def _on_castle_change(self):
        # チェックボックスの値は直接self.castle_*に反映済み
        self._update_fen()

    def _on_ep_change(self):
        self.enpassant = self.ep_ctrl.GetValue()
        self._update_fen()

    def _on_half_change(self):
        self.halfmove = self.half_ctrl.GetValue()
        self._update_fen()

    def _on_full_change(self):
        self.fullmove = self.full_ctrl.GetValue()
        self._update_fen()

if __name__ == "__main__":
    app = wx.App()
    frame = FenGUI(None)
    frame.Show()
    app.MainLoop()