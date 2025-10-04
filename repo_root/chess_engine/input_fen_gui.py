import tkinter as tk
from tkinter import messagebox

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

class FenGUI:
    def __init__(self, root):
        self.root = root
        root.title("FEN Maker (pieces + history options)")
        root.geometry("1000x660")

        # ---- state ----
        self.selected_piece = 'P'
        self.board = [['' for _ in range(8)] for _ in range(8)]
        self.side_to_move = tk.StringVar(value='w')   # w/b
        self.castle_k = tk.BooleanVar(value=True)     # K
        self.castle_q = tk.BooleanVar(value=True)     # Q
        self.castle_kb = tk.BooleanVar(value=True)    # k
        self.castle_qb = tk.BooleanVar(value=True)    # q
        self.enpassant = tk.StringVar(value='-')      # "-" or a3/e6
        self.halfmove = tk.StringVar(value='0')       # >=0
        self.fullmove = tk.StringVar(value='1')       # >=1

        self._build_ui()
        self._load_start_position()
        self._update_fen()

    # ---------- UI ----------
    def _build_ui(self):
        main = tk.Frame(self.root)
        main.pack(fill="both", expand=True, padx=10, pady=10)

        left = tk.Frame(main)
        left.pack(side="left", fill="y", padx=(0,12))

        center = tk.Frame(main)
        center.pack(side="left")

        right = tk.Frame(main)
        right.pack(side="left", fill="y", padx=(12,0))

        # --- Palette ---
        tk.Label(left, text="Piece Palette", font=("Segoe UI", 11, "bold")).pack(pady=(0,6))
        palette = tk.Frame(left); palette.pack()
        row1 = tk.Frame(palette); row1.pack()
        for p in ['K','Q','R','B','N','P']:
            self._make_palette_btn(row1, p)
        row2 = tk.Frame(palette); row2.pack(pady=(4,0))
        for p in ['k','q','r','b','n','p']:
            self._make_palette_btn(row2, p)

        tk.Button(left, text="Eraser (空)", command=lambda: self._select_piece(''), width=14).pack(pady=6)
        self.sel_lbl = tk.Label(left, text="Selected: ♙ (P)", font=("Segoe UI", 10))
        self.sel_lbl.pack(pady=(0,10))

        # convenience
        tk.Button(left, text="Start pos", width=14, command=self._load_start_position).pack(pady=(0,2))
        tk.Button(left, text="Clear board", width=14, command=self._clear_board).pack(pady=(0,10))

        # FEN I/O
        fen_box = tk.LabelFrame(left, text="FEN")
        fen_box.pack(fill="x", pady=8)
        self.fen_text = tk.Text(fen_box, height=3, wrap="word")
        self.fen_text.pack(fill="x")
        row = tk.Frame(fen_box); row.pack(anchor="e", fill="x")
        tk.Button(row, text="Copy", command=self._copy_fen).pack(side="right", padx=(6,0))
        tk.Button(row, text="Load FEN", command=self._load_fen_from_text).pack(side="right")

        # --- Board ---
        board_frame = tk.Frame(center, bd=2, relief="groove")
        board_frame.pack()
        self.sq_buttons = []
        for y in range(8):
            rf = tk.Frame(board_frame); rf.pack()
            row_buttons = []
            for x in range(8):
                bg = LIGHT_COLOR if (x + y) % 2 == 0 else DARK_COLOR
                btn = tk.Button(rf, text='', width=4, height=2, font=("Segoe UI Symbol", 20),
                                bg=bg, fg="black",
                                command=lambda yy=y, xx=x: self._place_on_square(yy, xx))
                btn.bind("<Button-3>", lambda e, yy=y, xx=x: self._erase_square(yy, xx))
                btn.pack(side="left")
                row_buttons.append(btn)
            self.sq_buttons.append(row_buttons)
        tk.Label(center, text="左クリック: 置く／差し替え   右クリック: 消す", fg="#555").pack(pady=(6,0))

        # --- History Options ---
        tk.Label(right, text="History options", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0,6))

        # side to move
        stm = tk.LabelFrame(right, text="Side to move")
        stm.pack(anchor="w", fill="x", padx=2, pady=2)
        tk.Radiobutton(stm, text="White (w)", variable=self.side_to_move, value='w', command=self._update_fen).pack(anchor="w")
        tk.Radiobutton(stm, text="Black (b)", variable=self.side_to_move, value='b', command=self._update_fen).pack(anchor="w")

        # castling rights
        cas = tk.LabelFrame(right, text="Castling rights (資格の有無)")
        cas.pack(anchor="w", fill="x", padx=2, pady=2)
        tk.Checkbutton(cas, text="K  (White short)", var=self.castle_k, command=self._update_fen).pack(anchor="w")
        tk.Checkbutton(cas, text="Q  (White long)",  var=self.castle_q, command=self._update_fen).pack(anchor="w")
        tk.Checkbutton(cas, text="k  (Black short)", var=self.castle_kb, command=self._update_fen).pack(anchor="w")
        tk.Checkbutton(cas, text="q  (Black long)",  var=self.castle_qb, command=self._update_fen).pack(anchor="w")
        tk.Button(cas, text="Suggest castling (盤面から推定)", command=self._suggest_castling).pack(anchor="w", pady=(4,0))

        # en passant
        epf = tk.LabelFrame(right, text="En passant target")
        epf.pack(anchor="w", fill="x", padx=2, pady=2)
        tk.Label(epf, text="Square (- / a3..h3 / a6..h6)").pack(anchor="w")
        e = tk.Entry(epf, textvariable=self.enpassant)
        e.pack(anchor="w", fill="x"); e.bind("<KeyRelease>", lambda _ : self._update_fen())

        # clocks
        clk = tk.LabelFrame(right, text="Clocks")
        clk.pack(anchor="w", fill="x", padx=2, pady=2)
        rowc = tk.Frame(clk); rowc.pack(anchor="w", fill="x")
        tk.Label(rowc, text="Halfmove (>=0):").pack(side="left")
        he = tk.Entry(rowc, width=7, textvariable=self.halfmove)
        he.pack(side="left", padx=(4,10)); he.bind("<KeyRelease>", lambda _ : self._update_fen())
        tk.Label(rowc, text="Fullmove (>=1):").pack(side="left")
        fe = tk.Entry(rowc, width=7, textvariable=self.fullmove)
        fe.pack(side="left", padx=4); fe.bind("<KeyRelease>", lambda _ : self._update_fen())

        tk.Label(right, text="※ キャスリング権は“可能性”ではなく“資格”。\n※ EPは直前手で2歩前進があり、かつ捕獲可能な時のみ。", fg="#666", justify="left").pack(anchor="w", pady=(6,0))

    def _make_palette_btn(self, parent, piece_code):
        btn = tk.Button(parent, text=UNICODE[piece_code], width=4, font=("Segoe UI Symbol", 16),
                        command=lambda p=piece_code: self._select_piece(p))
        btn.pack(side="left", padx=2)

    def _select_piece(self, p):
        self.selected_piece = p
        sym = UNICODE[p] if p else '∅'
        tag = p.upper() if p else 'empty'
        self.sel_lbl.config(text=f"Selected: {sym} ({tag})")

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
        self.sq_buttons[y][x].config(text=UNICODE[self.board[y][x]])

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
        # 実用上は rank 3 or 6 のみを許可（2歩前進直後の着地点）
        return (f in FILES) and (r in "36")

    def _castling_rights_str(self):
        out = ''
        if self.castle_k.get():  out += 'K'
        if self.castle_q.get():  out += 'Q'
        if self.castle_kb.get(): out += 'k'
        if self.castle_qb.get(): out += 'q'
        return out if out else '-'

    def _suggest_castling(self):
        """盤面から“権利候補”を推定（歴史は復元不可なので目安）。"""
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

        self.castle_k.set(k); self.castle_q.set(q)
        self.castle_kb.set(kb); self.castle_qb.set(qb)
        self._update_fen()

    def _current_fen(self):
        placement = self._board_to_fen_placement()
        stm = self.side_to_move.get()
        cast = self._castling_rights_str()
        ep = self.enpassant.get().strip()
        ep = ep if self._valid_ep(ep) else '-'
        hm = self.halfmove.get().strip()
        fm = self.fullmove.get().strip()
        hm = hm if hm.isdigit() and int(hm) >= 0 else '0'
        fm = fm if fm.isdigit() and int(fm) >= 1 else '1'
        return f"{placement} {stm} {cast} {ep} {hm} {fm}"

    def _update_fen(self):
        fen = self._current_fen()
        self.fen_text.delete("1.0", "end")
        self.fen_text.insert("1.0", fen)

    def _clear_board(self):
        self.board = [['' for _ in range(8)] for _ in range(8)]
        # 手番・権利・EP・時計は好みで保持／リセット。ここでは初期化。
        self.side_to_move.set('w')
        for v, val in [(self.castle_k,False),(self.castle_q,False),(self.castle_kb,False),(self.castle_qb,False)]:
            v.set(val)
        self.enpassant.set('-'); self.halfmove.set('0'); self.fullmove.set('1')
        self._render_all(); self._update_fen()

    def _load_start_position(self):
        start = [
            list("rnbqkbnr"),
            list("pppppppp"),
            ['']*8, ['']*8, ['']*8, ['']*8,
            list("PPPPPPPP"),
            list("RNBQKBNR"),
        ]
        self.board = start
        self.side_to_move.set('w')
        self.castle_k.set(True); self.castle_q.set(True)
        self.castle_kb.set(True); self.castle_qb.set(True)
        self.enpassant.set('-'); self.halfmove.set('0'); self.fullmove.set('1')
        self._render_all(); self._update_fen()

    def _copy_fen(self):
        fen = self.fen_text.get("1.0", "end").strip()
        self.root.clipboard_clear()
        self.root.clipboard_append(fen)
        self.root.update()
        messagebox.showinfo("Copied", "FENをクリップボードにコピーしました。")

    # ---------- FEN load ----------
    def _load_fen_from_text(self):
        fen = self.fen_text.get("1.0", "end").strip()
        try:
            self._load_fen(fen)
            self._render_all()
            self._update_fen()
        except Exception as e:
            messagebox.showerror("FEN読み込みエラー", f"不正なFENです。\n{e}")

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
        self.side_to_move.set(stm)

        self.castle_k.set('K' in cast)
        self.castle_q.set('Q' in cast)
        self.castle_kb.set('k' in cast)
        self.castle_qb.set('q' in cast)
        if cast == '-':
            self.castle_k.set(False); self.castle_q.set(False)
            self.castle_kb.set(False); self.castle_qb.set(False)

        if not self._valid_ep(ep):
            raise ValueError("en passant は '-' か rank 3/6 のマス名を入力。")
        self.enpassant.set(ep)

        if not hm.isdigit() or int(hm) < 0:
            raise ValueError("halfmove は0以上の整数。")
        if not fm.isdigit() or int(fm) < 1:
            raise ValueError("fullmove は1以上の整数。")
        self.halfmove.set(hm); self.fullmove.set(fm)

if __name__ == "__main__":
    root = tk.Tk()
    app = FenGUI(root)
    root.mainloop()
