"""タッチ操作向けの画面（Tkinter）。

起動:
    python -m bale_planner.app                # 通常起動（データは %LOCALAPPDATA%/BalePlanner）
    python -m bale_planner.app --demo         # デモデータ入りの一時DBで起動
    python -m bale_planner.app --fullscreen   # タブレット向け全画面
"""
from __future__ import annotations

import argparse
import datetime as dt
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, ttk

from . import workcalendar as wc
from .db import Repository, default_db_path
from .models import Carrier, Mode, Settings, Shipment, Slot, StockReading, StockTiming
from .service import PlanView, compute, seed_demo

FONT = "Yu Gothic UI"
WEEKDAYS = "月火水木金土日"

BG = "#f4f5f7"
CARD = "#ffffff"
TEXT = "#1f2328"
MUTED = "#59636e"
PRIMARY = "#1f6feb"
PRIMARY_TEXT = "#ffffff"
DANGER = "#d1242f"
DANGER_BG = "#ffe3e3"
INFO_BG = "#fff6d6"
HOLIDAY_BG = "#e6e9ee"
LOCK_BG = "#e3eeff"
BORDER = "#d0d7de"
BUTTON_BG = "#e6ebf1"  # 押せる場所が分かるよう背景と区別する


def f(size: int, weight: str = "normal"):
    return (FONT, size, weight)


def fmt_date(d: dt.date) -> str:
    return f"{d:%m/%d}({WEEKDAYS[d.weekday()]})"


def button(parent, text, command, kind="normal", size=16, **kw):
    colors = {
        "normal": (BUTTON_BG, TEXT, BORDER),
        "primary": (PRIMARY, PRIMARY_TEXT, PRIMARY),
        "danger": (BUTTON_BG, DANGER, DANGER),
    }[kind]
    b = tk.Button(
        parent,
        text=text,
        command=command,
        font=f(size, "bold" if kind == "primary" else "normal"),
        bg=colors[0],
        fg=colors[1],
        activebackground=colors[0],
        activeforeground=colors[1],
        relief="flat",
        bd=0,
        highlightthickness=2,
        highlightbackground=colors[2],
        padx=kw.pop("padx", 18),
        pady=kw.pop("pady", 10),
        cursor="hand2",
        **kw,
    )
    return b


class Segmented(tk.Frame):
    """タッチしやすい切り替えボタン群。"""

    def __init__(self, parent, options, variable: tk.StringVar, command=None, size=16, bg=BG, wrap=0):
        super().__init__(parent, bg=bg)
        self.var = variable
        self.command = command
        self.buttons: dict[str, tk.Button] = {}
        for i, (value, label) in enumerate(options):
            b = tk.Button(
                self, text=label, font=f(size), relief="flat", bd=0, padx=16, pady=8, cursor="hand2",
                highlightthickness=2, command=lambda v=value: self.select(v),
            )
            r, c = (divmod(i, wrap) if wrap else (0, i))
            b.grid(row=r, column=c, padx=3, pady=3, sticky="ew")
            self.buttons[value] = b
        self.refresh()

    def select(self, value):
        self.var.set(value)
        self.refresh()
        if self.command:
            self.command(value)

    def refresh(self):
        for v, b in self.buttons.items():
            on = v == self.var.get()
            b.configure(
                bg=PRIMARY if on else BUTTON_BG, fg=PRIMARY_TEXT if on else TEXT,
                activebackground=PRIMARY if on else BUTTON_BG, highlightbackground=PRIMARY if on else BORDER,
            )


# ---------------------------------------------------------------------------
# ダイアログ
# ---------------------------------------------------------------------------


class _Dialog(tk.Toplevel):
    def __init__(self, parent, title):
        super().__init__(parent)
        self.title(title)
        self.configure(bg=BG, padx=20, pady=16)
        self.transient(parent.winfo_toplevel())
        self.resizable(False, False)
        self.result = None
        self.bind("<Escape>", lambda e: self.destroy())

    def show(self):
        self.update_idletasks()
        top = self.master.winfo_toplevel()
        x = top.winfo_rootx() + (top.winfo_width() - self.winfo_width()) // 2
        y = top.winfo_rooty() + (top.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
        self.grab_set()
        self.focus_set()
        self.wait_window()
        return self.result


class NumberDialog(_Dialog):
    """画面上のテンキーで数値を入力する。choices を渡すと上部に選択ボタンを出す。"""

    def __init__(self, parent, title, initial=None, decimal=False, info="", choices=None, choice=None,
                 min_value=0, max_value=None):
        super().__init__(parent, title)
        self.decimal, self.min_value, self.max_value = decimal, min_value, max_value
        self.fresh = True
        self.text = tk.StringVar(value="" if initial is None else _num_str(initial))
        self.choice = tk.StringVar(value=choice or (choices[0][0] if choices else ""))

        tk.Label(self, text=title, font=f(18, "bold"), bg=BG, fg=TEXT).pack(anchor="w")
        if info:
            tk.Label(self, text=info, font=f(13), bg=BG, fg=MUTED, justify="left").pack(anchor="w", pady=(2, 6))
        if choices:
            Segmented(self, choices, self.choice, size=16).pack(fill="x", pady=(4, 8))
        tk.Label(self, textvariable=self.text, font=f(34, "bold"), bg=CARD, fg=TEXT, anchor="e",
                 padx=16, pady=4, relief="solid", bd=1, width=9).pack(fill="x", pady=6)
        self.error = tk.Label(self, text="", font=f(12), bg=BG, fg=DANGER)
        self.error.pack(anchor="w")

        pad = tk.Frame(self, bg=BG)
        pad.pack(pady=4)
        keys = ["7", "8", "9", "4", "5", "6", "1", "2", "3", "." if decimal else "C", "0", "⌫"]
        for i, k in enumerate(keys):
            b = button(pad, k, lambda k=k: self.press(k), size=22, width=3, pady=8)
            b.grid(row=i // 3, column=i % 3, padx=4, pady=4)
        if decimal:
            button(pad, "C", lambda: self.press("C"), size=16).grid(row=4, column=0, columnspan=3, sticky="ew", padx=4)

        row = tk.Frame(self, bg=BG)
        row.pack(fill="x", pady=(10, 0))
        button(row, "キャンセル", self.destroy).pack(side="left", expand=True, fill="x", padx=(0, 6))
        button(row, "決定", self.ok, kind="primary").pack(side="left", expand=True, fill="x", padx=(6, 0))
        self.bind("<Return>", lambda e: self.ok())
        for k in "0123456789":
            self.bind(k, lambda e, k=k: self.press(k))
        self.bind("<BackSpace>", lambda e: self.press("⌫"))

    def press(self, k):
        cur = "" if self.fresh and k not in ("⌫",) else self.text.get()
        self.fresh = False
        if k == "C":
            cur = ""
        elif k == "⌫":
            cur = cur[:-1]
        elif k == ".":
            if "." not in cur:
                cur = (cur or "0") + "."
        elif len(cur) < 7:
            cur = cur + k
        self.text.set(cur)
        self.error.configure(text="")

    def ok(self):
        raw = self.text.get()
        try:
            value = float(raw) if self.decimal else int(raw)
        except ValueError:
            self.error.configure(text="数値を入力してください")
            return
        if value < self.min_value or (self.max_value is not None and value > self.max_value):
            hi = f"〜{_num_str(self.max_value)}" if self.max_value is not None else "以上"
            self.error.configure(text=f"{_num_str(self.min_value)}{hi} の範囲で入力してください")
            return
        self.result = (self.choice.get(), value) if self.choice.get() else value
        self.destroy()


def _num_str(v) -> str:
    return f"{v:g}" if isinstance(v, float) else str(v)


class DateDialog(_Dialog):
    """カレンダーから日付を選ぶ。"""

    def __init__(self, parent, title, initial: dt.date, today: dt.date, overrides=None, weeks=6):
        super().__init__(parent, title)
        tk.Label(self, text=title, font=f(18, "bold"), bg=BG, fg=TEXT).pack(anchor="w", pady=(0, 8))
        grid = tk.Frame(self, bg=BG)
        grid.pack()
        for c, w in enumerate(WEEKDAYS):
            tk.Label(grid, text=w, font=f(13), bg=BG, fg=DANGER if c == 6 else MUTED).grid(row=0, column=c)
        first = today - dt.timedelta(days=today.weekday() + 7)
        for i in range(weeks * 7):
            d = first + dt.timedelta(days=i)
            holiday = wc.is_holiday(d, overrides)
            sel = d == initial
            label = f"{d.month}/{d.day}" if d.day == 1 or i == 0 else str(d.day)
            b = tk.Button(
                grid, text=label, width=4, font=f(15, "bold" if d == today else "normal"),
                relief="flat", bd=0, pady=8, highlightthickness=2, cursor="hand2",
                bg=PRIMARY if sel else (HOLIDAY_BG if holiday else CARD),
                fg=PRIMARY_TEXT if sel else (DANGER if holiday else TEXT),
                highlightbackground=PRIMARY if d == today else BORDER,
                command=lambda d=d: self.pick(d),
            )
            b.grid(row=1 + i // 7, column=i % 7, padx=2, pady=2)
        tk.Label(self, text="灰色＝休業日　枠線＝今日", font=f(12), bg=BG, fg=MUTED).pack(anchor="w", pady=(8, 0))
        button(self, "キャンセル", self.destroy).pack(fill="x", pady=(8, 0))

    def pick(self, d):
        self.result = d
        self.destroy()


# ---------------------------------------------------------------------------
# アプリ本体
# ---------------------------------------------------------------------------


class App(tk.Tk):
    def __init__(self, repo: Repository, today: dt.date | None = None, fullscreen: bool = False):
        super().__init__()
        self.repo = repo
        self.today = today or dt.date.today()
        self.view: PlanView | None = None
        self.title("ベール製造計画")
        self.configure(bg=BG)
        self.geometry("1280x800")
        self.minsize(1024, 700)
        try:
            self.state("zoomed")  # Windows では最大化して起動
        except tk.TclError:
            pass
        if fullscreen:
            self.attributes("-fullscreen", True)
            self.bind("<F11>", lambda e: self.attributes("-fullscreen", not self.attributes("-fullscreen")))
        self._style()

        header = tk.Frame(self, bg=CARD, padx=16, pady=8, highlightthickness=1, highlightbackground=BORDER)
        header.pack(fill="x")
        tk.Label(header, text="ベール製造計画", font=f(20, "bold"), bg=CARD, fg=TEXT).pack(side="left")
        self.date_label = tk.Label(header, text="", font=f(16), bg=CARD, fg=MUTED)
        self.date_label.pack(side="left", padx=20)
        self.mode_var = tk.StringVar(value=repo.get_mode().value)
        Segmented(header, [(Mode.MIN.value, "在庫最小化"), (Mode.MAX.value, "在庫最大化")], self.mode_var,
                  command=self.change_mode, bg=CARD).pack(side="right")
        tk.Label(header, text="計画モード", font=f(14), bg=CARD, fg=MUTED).pack(side="right", padx=8)

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)
        nav = tk.Frame(body, bg=CARD, padx=8, pady=8, highlightthickness=1, highlightbackground=BORDER)
        nav.pack(side="left", fill="y")
        self.content = tk.Frame(body, bg=BG, padx=16, pady=12)
        self.content.pack(side="left", fill="both", expand=True)

        self.screens = {
            "main": MainScreen(self.content, self),
            "plan": PlanScreen(self.content, self),
            "ship": ShipmentScreen(self.content, self),
            "settings": SettingsScreen(self.content, self),
        }
        self.nav_var = tk.StringVar(value="main")
        Segmented(nav, [("main", "今日"), ("plan", "2週間計画"), ("ship", "出荷予定"), ("settings", "設定")],
                  self.nav_var, command=self.show, size=17, bg=CARD, wrap=1).pack(fill="x")
        self.current = "main"
        self.refresh()
        self.show("main")

    def _style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        # 行の高さはピクセル指定のため、DPI に応じたフォント高さから決める
        line = tkfont.Font(root=self, font=f(14)).metrics("linespace")
        s.configure("Treeview", font=f(14), rowheight=int(line * 1.6), background=CARD, fieldbackground=CARD,
                    foreground=TEXT)
        s.configure("Treeview.Heading", font=f(13, "bold"), background=HOLIDAY_BG, foreground=TEXT, padding=6)
        s.map("Treeview", background=[("selected", PRIMARY)], foreground=[("selected", PRIMARY_TEXT)])
        s.configure("Vertical.TScrollbar", arrowsize=int(line * 1.2), width=int(line * 1.2))

    # ---- 共通操作 --------------------------------------------------------

    def show(self, name: str):
        for scr in self.screens.values():
            scr.pack_forget()
        self.current = name
        self.nav_var.set(name)
        self.screens[name].pack(fill="both", expand=True)
        self.screens[name].refresh()

    def refresh(self):
        """データを読み直して計画を再計算し、表示中の画面を更新する。"""
        self.view = compute(self.repo, self.today, Mode(self.mode_var.get()))
        self.date_label.configure(text=f"今日 {self.today:%Y/%m/%d}({WEEKDAYS[self.today.weekday()]})")
        if self.current in self.screens:
            self.screens[self.current].refresh()

    def change_mode(self, value: str):
        self.repo.set_mode(Mode(value))
        self.refresh()

    def record_stock(self, timing: StockTiming, quantity: int, date: dt.date | None = None):
        self.repo.add_stock_reading(StockReading(date or self.today, timing, quantity))
        self.refresh()

    def set_production(self, date: dt.date, slot: Slot, bales: int | None):
        """製造数を手動確定する（None で自動計算に戻す）。翌日以降は自動再計算される。"""
        if bales is None:
            self.repo.clear_lock(date, slot)
        else:
            self.repo.set_lock(date, slot, bales)
        self.refresh()

    def ask_stock(self):
        default = StockTiming.START.value if dt.datetime.now().hour < 12 else StockTiming.END.value
        res = NumberDialog(
            self, "実在庫を入力", info="現場で数えたベール数を入力してください。",
            choices=[(StockTiming.START.value, "始業時"), (StockTiming.END.value, "終業時")], choice=default,
            max_value=9999,
        ).show()
        if res:
            self.record_stock(StockTiming(res[0]), res[1])

    def ask_production(self, date: dt.date, slot: Slot):
        if not self.view:
            return
        sp = getattr(self.view.plan.day(date), "am" if slot is Slot.AM else "pm")
        st = self.repo.get_settings()
        info = (
            f"{fmt_date(date)} {slot.label}　現在の計画: {sp.production} ベール（{sp.total_minutes} 分）\n"
            f"能力 {st.bales_per_hour:g} ベール/時。確定すると翌日以降を自動で再計算します。"
        )
        res = NumberDialog(self, f"{slot.label}の製造数を変更", initial=sp.production, info=info, max_value=999).show()
        if res is not None:
            self.set_production(date, slot, res)


class Screen(tk.Frame):
    def __init__(self, parent, app: App):
        super().__init__(parent, bg=BG)
        self.app = app

    def refresh(self):
        pass


def card(parent, title):
    fr = tk.Frame(parent, bg=CARD, padx=18, pady=12, highlightthickness=1, highlightbackground=BORDER)
    tk.Label(fr, text=title, font=f(15, "bold"), bg=CARD, fg=MUTED).pack(anchor="w")
    return fr


# ---- メイン画面 --------------------------------------------------------------


class MainScreen(Screen):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.banner = tk.Label(self, text="", font=f(15, "bold"), bg=INFO_BG, fg=TEXT, anchor="w", padx=12, pady=8)
        self.day_label = tk.Label(self, text="", font=f(18, "bold"), bg=BG, fg=TEXT, anchor="w")
        self.day_label.pack(fill="x", pady=(0, 8))

        grid = tk.Frame(self, bg=BG)
        grid.pack(fill="both", expand=True)
        grid.columnconfigure((0, 1, 2), weight=1, uniform="c")
        grid.rowconfigure(1, weight=1)

        c1 = card(grid, "出荷予定")
        c1.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.ship_big = tk.Label(c1, font=f(34, "bold"), bg=CARD, fg=TEXT)
        self.ship_big.pack(anchor="w")
        self.ship_detail = tk.Label(c1, font=f(14), bg=CARD, fg=TEXT, justify="left", anchor="w")
        self.ship_detail.pack(anchor="w", fill="x")

        c2 = card(grid, "推奨製造")
        c2.grid(row=0, column=1, sticky="nsew", padx=8)
        self.prod_big = tk.Label(c2, font=f(34, "bold"), bg=CARD, fg=PRIMARY)
        self.prod_big.pack(anchor="w")
        self.prod_am = tk.Label(c2, font=f(15), bg=CARD, fg=TEXT, anchor="w")
        self.prod_am.pack(anchor="w", fill="x")
        self.prod_pm = tk.Label(c2, font=f(15), bg=CARD, fg=TEXT, anchor="w")
        self.prod_pm.pack(anchor="w", fill="x")

        c3 = card(grid, "終業時の予測在庫")
        c3.grid(row=0, column=2, sticky="nsew", padx=(8, 0))
        self.inv_big = tk.Label(c3, font=f(34, "bold"), bg=CARD, fg=TEXT)
        self.inv_big.pack(anchor="w")
        self.inv_detail = tk.Label(c3, font=f(14), bg=CARD, fg=MUTED, justify="left", anchor="w")
        self.inv_detail.pack(anchor="w", fill="x")

        c4 = card(grid, "警告・お知らせ")
        c4.grid(row=1, column=0, columnspan=3, sticky="nsew", pady=(12, 0))
        self.warn_box = tk.Frame(c4, bg=CARD)
        self.warn_box.pack(fill="both", expand=True)

        actions = tk.Frame(self, bg=BG)
        actions.pack(fill="x", pady=(12, 0))
        button(actions, "実在庫を入力", app.ask_stock, kind="primary", size=18).pack(side="left", padx=(0, 10))
        self.btn_am = button(actions, "午前の製造数を変更", lambda: self._change(Slot.AM), size=17)
        self.btn_am.pack(side="left", padx=10)
        self.btn_pm = button(actions, "午後の製造数を変更", lambda: self._change(Slot.PM), size=17)
        self.btn_pm.pack(side="left", padx=10)
        self.btn_auto = button(actions, "自動計算に戻す", self._reset, size=17)
        self.btn_auto.pack(side="left", padx=10)
        self.target: dt.date | None = None

    def _change(self, slot):
        if self.target:
            self.app.ask_production(self.target, slot)

    def _reset(self):
        if self.target:
            for s in (Slot.AM, Slot.PM):
                self.app.repo.clear_lock(self.target, s)
            self.app.refresh()

    def refresh(self):
        v = self.app.view
        self.banner.pack_forget()
        for w in self.warn_box.winfo_children():
            w.destroy()
        if v is None:
            self.target = None
            self._banner("実在庫がまだ入力されていません。「実在庫を入力」から登録してください。")
            for lbl in (self.ship_big, self.prod_big, self.inv_big):
                lbl.configure(text="—")
            for lbl in (self.ship_detail, self.prod_am, self.prod_pm, self.inv_detail):
                lbl.configure(text="")
            self.day_label.configure(text="")
            return

        plan = v.plan
        dates = [d.date for d in plan.days]
        self.target = v.today if v.today in dates else plan.days[0].date
        day = plan.day(self.target)
        st = self.app.repo.get_settings()
        if self.target == v.today:
            self.day_label.configure(text=f"本日 {fmt_date(self.target)} の計画（{plan.mode.label}）")
        else:
            self.day_label.configure(text=f"本日の終業在庫は入力済みです。翌日 {fmt_date(self.target)} の計画（{plan.mode.label}）")
        if v.stale_days >= 1:
            self._banner(f"実在庫の入力が {v.stale_days} 日前のものです。現場で数えて入力すると計画が正確になります。")
        if not wc.is_production_day(self.target, self.app.repo.get_overrides()):
            self._banner(f"{fmt_date(self.target)} は休業日です。")

        ships = [s for s in v.shipments if s.date == self.target]
        trucks = sum(s.trucks for s in ships)
        self.ship_big.configure(text=f"{trucks} 台 / {day.shipment} ベール" if ships else "出荷なし")
        lines = [f"{s.slot.label}  {s.carrier.name} {s.trucks}台  {s.quantity} ベール" for s in ships]
        for sp in (day.am, day.pm):
            if sp.shortage:
                lines.append(f"⚠ {sp.slot.label}は {sp.shortage} ベール不足")
        self.ship_detail.configure(text="\n".join(lines), fg=DANGER if any(sp.shortage for sp in (day.am, day.pm)) else TEXT)

        self.prod_big.configure(text=f"{day.production} ベール")
        self.prod_am.configure(text=self._slot_text(day.am))
        self.prod_pm.configure(text=self._slot_text(day.pm))

        over = day.inventory_end > st.storage_cap
        self.inv_big.configure(text=f"{day.inventory_end} ベール", fg=DANGER if over else TEXT)
        self.inv_detail.configure(
            text=f"保管上限 {st.storage_cap}（空き {max(0, st.storage_cap - day.inventory_end)}）\n午前終了時 {day.am.inventory_end} ベール"
        )

        today_w = [w for w in plan.warnings if w.date == self.target]
        upcoming = [w for w in plan.errors if w.date and w.date > self.target]
        if not today_w and not upcoming:
            tk.Label(self.warn_box, text="問題はありません。", font=f(15), bg=CARD, fg=MUTED).pack(anchor="w")
        for w in today_w[:4]:
            self._warn_line(w, prefix="本日")
        for w in upcoming[:3]:
            self._warn_line(w, prefix=fmt_date(w.date))
        if len(upcoming) > 3:
            tk.Label(self.warn_box, text=f"ほか {len(upcoming) - 3} 件 →「2週間計画」で確認", font=f(13),
                     bg=CARD, fg=MUTED).pack(anchor="w")
        locked = day.am.locked or day.pm.locked
        self.btn_auto.configure(state="normal" if locked else "disabled")

    def _slot_text(self, sp):
        if not sp.production:
            return f"{sp.slot.label}  製造なし" + ("（手動）" if sp.locked else "")
        extra = []
        if sp.overtime_minutes:
            extra.append(f"うち残業 {sp.overtime_minutes} 分")
        if sp.holiday_minutes:
            extra.append("休日出勤")
        if sp.locked:
            extra.append("手動")
        tail = f"（{'・'.join(extra)}）" if extra else ""
        return f"{sp.slot.label}  {sp.production} ベール  運転 {sp.total_minutes} 分{tail}"

    def _warn_line(self, w, prefix):
        err = w.level == "error"
        fr = tk.Frame(self.warn_box, bg=DANGER_BG if err else INFO_BG, padx=10, pady=4)
        fr.pack(fill="x", pady=2)
        slot = f" {w.slot.label}" if w.slot else ""
        tk.Label(fr, text=f"{'要対応' if err else 'お知らせ'}｜{prefix}{slot}  {w.message}", font=f(14, "bold" if err else "normal"),
                 bg=fr["bg"], fg=DANGER if err else TEXT, anchor="w", justify="left", wraplength=self._wrap()).pack(anchor="w")
        if w.suggestions:
            tk.Label(fr, text="対策: " + " ／ ".join(w.suggestions[:3]), font=f(13), bg=fr["bg"], fg=TEXT,
                     anchor="w", justify="left", wraplength=self._wrap()).pack(anchor="w")

    def _wrap(self) -> int:
        """警告文の折り返し幅（画面幅に合わせる）。"""
        w = self.warn_box.winfo_width()
        return max(400, w - 40) if w > 100 else max(400, self.winfo_toplevel().winfo_width() - 400)

    def _banner(self, text):
        self.banner.configure(text=text)
        self.banner.pack(fill="x", pady=(0, 8), before=self.day_label)


# ---- 2週間計画画面 -----------------------------------------------------------


class PlanScreen(Screen):
    COLS = [
        ("date", "日付", 110), ("am_ship", "午前出荷", 250), ("am_prod", "午前製造", 160), ("am_inv", "午前末", 70),
        ("pm_ship", "午後出荷", 250), ("pm_prod", "午後製造", 190), ("pm_inv", "終業在庫", 80),
    ]

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.summary = tk.Label(self, font=f(15), bg=BG, fg=TEXT, anchor="w")
        self.summary.pack(fill="x", pady=(0, 6))
        frame = tk.Frame(self, bg=BG)
        frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(frame, columns=[c[0] for c in self.COLS], show="headings", selectmode="browse", height=8)
        for key, label, width in self.COLS:
            anchor = "center" if key.endswith("inv") else "w"
            self.tree.heading(key, text=label, anchor=anchor)
            self.tree.column(key, width=width, anchor=anchor, stretch=True)
        self.tree.tag_configure("holiday", background=HOLIDAY_BG)
        self.tree.tag_configure("error", background=DANGER_BG)
        self.tree.tag_configure("locked", background=LOCK_BG)
        self.tree.tag_configure("today", font=f(14, "bold"))
        sb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        _enable_drag_scroll(self.tree)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._update_buttons())

        legend = tk.Label(self, text="灰＝休業日　赤＝要対応　青＝手動確定あり　製造欄: ベール数 (運転時間)",
                          font=f(12), bg=BG, fg=MUTED, anchor="w")
        legend.pack(fill="x", pady=(4, 0))

        actions = tk.Frame(self, bg=BG)
        actions.pack(fill="x", pady=8)
        tk.Label(actions, text="選択した日：", font=f(15), bg=BG, fg=TEXT).pack(side="left")
        self.btn_am = button(actions, "午前の製造数を変更", lambda: self._change(Slot.AM))
        self.btn_am.pack(side="left", padx=6)
        self.btn_pm = button(actions, "午後の製造数を変更", lambda: self._change(Slot.PM))
        self.btn_pm.pack(side="left", padx=6)
        self.btn_auto = button(actions, "自動計算に戻す", self._reset)
        self.btn_auto.pack(side="left", padx=6)

        self.warnings = tk.Listbox(self, font=f(13), height=6, bg=CARD, fg=TEXT, relief="flat",
                                   highlightthickness=1, highlightbackground=BORDER, activestyle="none")
        self.warnings.pack(fill="x")

    def selected_date(self) -> dt.date | None:
        sel = self.tree.selection()
        return dt.date.fromisoformat(sel[0]) if sel else None

    def _change(self, slot):
        d = self.selected_date()
        if d:
            self.app.ask_production(d, slot)

    def _reset(self):
        d = self.selected_date()
        if d:
            for s in (Slot.AM, Slot.PM):
                self.app.repo.clear_lock(d, s)
            self.app.refresh()

    def _update_buttons(self):
        state = "normal" if self.selected_date() else "disabled"
        for b in (self.btn_am, self.btn_pm, self.btn_auto):
            b.configure(state=state)

    def refresh(self):
        keep = self.selected_date()
        self.tree.delete(*self.tree.get_children())
        self.warnings.delete(0, "end")
        v = self.app.view
        if v is None:
            self.summary.configure(text="実在庫を入力すると計画が表示されます。")
            self._update_buttons()
            return
        st = self.app.repo.get_settings()
        self.summary.configure(
            text=f"{v.plan.mode.label}　起点在庫 {v.plan.start_inventory}（{fmt_date(v.start)}）　保管上限 {st.storage_cap}"
            + (f"　期間末目標 {st.target_end_inventory}" if v.plan.mode is Mode.MAX else "")
        )
        err_slots = {(w.date, w.slot) for w in v.plan.errors}
        err_dates = {w.date for w in v.plan.errors}
        for day in v.visible_days:
            tags = []
            if not day.am.production_day:
                tags.append("holiday")
            if day.am.locked or day.pm.locked:
                tags.append("locked")
            if day.date in err_dates or day.inventory_end > st.storage_cap:
                tags.append("error")
            if day.date == v.today:
                tags.append("today")
            self.tree.insert("", "end", iid=day.date.isoformat(), tags=tags, values=(
                fmt_date(day.date) + (" 休" if not day.am.production_day else ""),
                self._ship(v, day.am), self._prod(day.am), day.am.inventory_end,
                self._ship(v, day.pm), self._prod(day.pm), day.pm.inventory_end,
            ))
        visible = {d.date for d in v.visible_days}
        for w in v.plan.warnings:
            if w.date and w.date not in visible:
                continue
            when = (fmt_date(w.date) if w.date else "") + (f" {w.slot.label}" if w.slot else "")
            mark = "【要対応】" if w.level == "error" else "【お知らせ】"
            self.warnings.insert("end", f"{mark}{when} {w.message}")
            if w.level == "error":
                self.warnings.itemconfigure("end", fg=DANGER)
                for s in w.suggestions:
                    self.warnings.insert("end", f"　　→ {s}")
        if keep and self.tree.exists(keep.isoformat()):
            self.tree.selection_set(keep.isoformat())
        self._update_buttons()

    @staticmethod
    def _ship(v, sp):
        if not sp.shipment:
            return ""
        names = "+".join(f"{s.carrier.name}{s.trucks}" for s in v.shipments if s.date == sp.date and s.slot is sp.slot)
        text = f"{sp.shipment}  {names}"
        return text + (f"  不足{sp.shortage}" if sp.shortage else "")

    @staticmethod
    def _prod(sp):
        if not sp.production:
            return "手動 0" if sp.locked else ""
        tag = []
        if sp.overtime_minutes:
            tag.append(f"残{sp.overtime_minutes}")
        if sp.holiday_minutes:
            tag.append("休出")
        if sp.locked:
            tag.append("手動")
        return f"{sp.production} ({sp.total_minutes}分)" + (f" {' '.join(tag)}" if tag else "")


def _enable_drag_scroll(tree: ttk.Treeview):
    """指でなぞってスクロールできるようにする。"""
    state = {"y": None, "moved": False}

    def press(e):
        state["y"], state["moved"] = e.y, False

    def motion(e):
        if state["y"] is None:
            return
        dy = e.y - state["y"]
        if abs(dy) >= 30:
            tree.yview_scroll(-1 if dy > 0 else 1, "units")
            state["y"], state["moved"] = e.y, True

    tree.bind("<ButtonPress-1>", press, add="+")
    tree.bind("<B1-Motion>", motion, add="+")


# ---- 出荷予定画面 ------------------------------------------------------------


class ShipmentScreen(Screen):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        left = tk.Frame(self, bg=BG)
        left.pack(side="left", fill="both", expand=True)
        tk.Label(left, text="出荷予定（今日から3週間）", font=f(17, "bold"), bg=BG, fg=TEXT).pack(anchor="w", pady=(0, 6))
        cols = [("date", "日付", 120), ("slot", "時間帯", 80), ("carrier", "業者", 110), ("trucks", "台数", 70), ("qty", "ベール数", 110)]
        frame = tk.Frame(left, bg=BG)
        frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(frame, columns=[c[0] for c in cols], show="headings", selectmode="browse")
        for key, label, width in cols:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor="w")
        self.tree.tag_configure("bad", background=DANGER_BG)
        sb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        _enable_drag_scroll(self.tree)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._load_selected())

        form = tk.Frame(self, bg=CARD, padx=18, pady=14, highlightthickness=1, highlightbackground=BORDER)
        form.pack(side="left", fill="y", padx=(16, 0))
        self.form_title = tk.Label(form, text="新規登録", font=f(17, "bold"), bg=CARD, fg=TEXT)
        self.form_title.pack(anchor="w")

        self.date = app.today
        self.slot_var = tk.StringVar(value=Slot.AM.value)
        self.carrier_var = tk.StringVar()
        self.trucks = 1
        self.override: int | None = None
        self.editing_id: int | None = None

        self._label(form, "日付")
        self.date_btn = button(form, "", self._pick_date, size=17)
        self.date_btn.pack(fill="x")
        self.date_warn = tk.Label(form, text="", font=f(12), bg=CARD, fg=DANGER)
        self.date_warn.pack(anchor="w")
        self._label(form, "時間帯")
        Segmented(form, [(Slot.AM.value, "午前"), (Slot.PM.value, "午後")], self.slot_var, bg=CARD).pack(anchor="w")
        self._label(form, "運搬業者")
        self.carrier_box = tk.Frame(form, bg=CARD)
        self.carrier_box.pack(anchor="w")
        self._label(form, "トラック台数")
        tr = tk.Frame(form, bg=CARD)
        tr.pack(anchor="w")
        button(tr, "−", lambda: self._trucks(-1), size=20, width=2).pack(side="left")
        self.trucks_label = tk.Label(tr, text="1", font=f(26, "bold"), bg=CARD, fg=TEXT, width=3)
        self.trucks_label.pack(side="left")
        button(tr, "＋", lambda: self._trucks(1), size=20, width=2).pack(side="left")
        self._label(form, "出荷予定数")
        qr = tk.Frame(form, bg=CARD)
        qr.pack(fill="x")
        self.qty_label = tk.Label(qr, text="", font=f(20, "bold"), bg=CARD, fg=TEXT)
        self.qty_label.pack(side="left")
        button(qr, "数量を修正", self._edit_qty, size=14).pack(side="right")

        btns = tk.Frame(form, bg=CARD)
        btns.pack(fill="x", pady=(18, 0))
        button(btns, "保存", self.save, kind="primary", size=17).pack(side="left", expand=True, fill="x", padx=(0, 4))
        button(btns, "新規", self.new, size=17).pack(side="left", expand=True, fill="x", padx=4)
        self.del_btn = button(btns, "削除", self.delete, kind="danger", size=17)
        self.del_btn.pack(side="left", expand=True, fill="x", padx=(4, 0))
        self.carrier_seg: Segmented | None = None

    def _label(self, parent, text):
        tk.Label(parent, text=text, font=f(13), bg=CARD, fg=MUTED).pack(anchor="w", pady=(10, 2))

    def _carriers(self):
        return {str(c.id): c for c in self.app.repo.list_carriers()}

    def refresh(self):
        carriers = self.app.repo.list_carriers(active_only=True)
        for w in self.carrier_box.winfo_children():
            w.destroy()
        if carriers and self.carrier_var.get() not in {str(c.id) for c in carriers}:
            self.carrier_var.set(str(carriers[0].id))
        self.carrier_seg = Segmented(self.carrier_box, [(str(c.id), f"{c.name}（{c.standard_load}）") for c in carriers],
                                     self.carrier_var, command=lambda v: self._update_form(), bg=CARD, wrap=2, size=15)
        self.carrier_seg.pack(anchor="w")

        self.tree.delete(*self.tree.get_children())
        ov = self.app.repo.get_overrides()
        end = self.app.today + dt.timedelta(days=20)
        for s in self.app.repo.list_shipments(self.app.today, end):
            tags = [] if wc.is_shipping_day(s.date, ov) else ["bad"]
            qty = f"{s.quantity}" + ("（修正）" if s.quantity_override is not None else "")
            self.tree.insert("", "end", iid=str(s.id), tags=tags,
                             values=(fmt_date(s.date), s.slot.label, s.carrier.name, s.trucks, qty))
        self._update_form()

    def _update_form(self):
        self.date_btn.configure(text=fmt_date(self.date))
        ok = wc.is_shipping_day(self.date, self.app.repo.get_overrides())
        self.date_warn.configure(text="" if ok else "この日は出荷できない日です（休業日・土曜）")
        self.trucks_label.configure(text=str(self.trucks))
        c = self._carriers().get(self.carrier_var.get())
        auto = self.trucks * c.standard_load if c else 0
        if self.override is None:
            self.qty_label.configure(text=f"{auto} ベール（自動）", fg=TEXT)
        else:
            self.qty_label.configure(text=f"{self.override} ベール（修正）", fg=PRIMARY)
        self.form_title.configure(text="出荷予定を編集" if self.editing_id else "新規登録")
        self.del_btn.configure(state="normal" if self.editing_id else "disabled")

    def _pick_date(self):
        d = DateDialog(self, "出荷日を選択", self.date, self.app.today, self.app.repo.get_overrides()).show()
        if d:
            self.date = d
            self._update_form()

    def _trucks(self, delta):
        self.trucks = max(1, min(20, self.trucks + delta))
        self._update_form()

    def _edit_qty(self):
        c = self._carriers().get(self.carrier_var.get())
        res = NumberDialog(self, "出荷予定数を修正", initial=self.override or (self.trucks * c.standard_load if c else 0),
                           info="自動計算（台数×標準積載数）に戻すには 0 を入力", max_value=9999).show()
        if res is not None:
            self.override = res or None
            self._update_form()

    def new(self):
        self.tree.selection_remove(self.tree.selection())
        self.editing_id, self.override, self.trucks = None, None, 1
        self._update_form()

    def _load_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        s = next((x for x in self.app.repo.list_shipments() if x.id == int(sel[0])), None)
        if not s:
            return
        self.editing_id, self.date, self.trucks, self.override = s.id, s.date, s.trucks, s.quantity_override
        self.slot_var.set(s.slot.value)
        self.carrier_var.set(str(s.carrier.id))
        self._refresh_segments()
        self._update_form()

    def _refresh_segments(self):
        for w in self.winfo_children():
            for seg in _descendants(w):
                if isinstance(seg, Segmented):
                    seg.refresh()

    def save(self):
        c = self._carriers().get(self.carrier_var.get())
        if not c:
            return
        s = Shipment(self.date, Slot(self.slot_var.get()), c, self.trucks, self.override, self.editing_id)
        self.app.repo.save_shipment(s)
        self.editing_id = s.id
        self.app.refresh()
        if self.tree.exists(str(s.id)):
            self.tree.selection_set(str(s.id))

    def delete(self, confirm=True):
        if not self.editing_id:
            return
        if confirm and not messagebox.askyesno("削除の確認", "この出荷予定を削除しますか？", parent=self):
            return
        self.app.repo.delete_shipment(self.editing_id)
        self.new()
        self.app.refresh()


def _descendants(w):
    yield w
    for c in w.winfo_children():
        yield from _descendants(c)


# ---- 設定画面 ----------------------------------------------------------------


class SettingsScreen(Screen):
    FIELDS = [
        ("storage_cap", "保管上限", "ベール", False, 1, 9999),
        ("bales_per_hour", "標準製造能力", "ベール/時", True, 0.1, 999),
        ("am_minutes", "午前の稼働時間", "分", False, 0, 600),
        ("pm_minutes", "午後の稼働時間", "分", False, 0, 600),
        ("overtime_max_minutes", "残業上限（1日）", "分", False, 0, 600),
        ("target_end_inventory", "期間末目標在庫（最大化）", "ベール", False, 0, 9999),
        ("plan_days", "計画期間", "日", False, 1, 60),
    ]

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.columnconfigure((0, 1, 2), weight=1, uniform="s")
        self.rowconfigure(0, weight=1)

        basic = card(self, "基本設定")
        basic.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.value_buttons: dict[str, tk.Button] = {}
        for key, label, unit, dec, lo, hi in self.FIELDS:
            row = tk.Frame(basic, bg=CARD)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=label, font=f(14), bg=CARD, fg=TEXT).pack(side="left")
            b = button(row, "", lambda k=key: self._edit(k), size=15, padx=10, pady=4)
            b.pack(side="right")
            self.value_buttons[key] = b
        row = tk.Frame(basic, bg=CARD)
        row.pack(fill="x", pady=(10, 3))
        tk.Label(row, text="休日出勤を自動で使う", font=f(14), bg=CARD, fg=TEXT).pack(side="left")
        self.hw_var = tk.StringVar()
        self.hw_seg = Segmented(row, [("1", "使う"), ("0", "使わない")], self.hw_var, command=self._set_hw, bg=CARD, size=14)
        self.hw_seg.pack(side="right")

        carriers = card(self, "運搬業者")
        carriers.grid(row=0, column=1, sticky="nsew", padx=8)
        self.ctree = ttk.Treeview(carriers, columns=("name", "load", "active"), show="headings", height=6, selectmode="browse")
        for k, t, w in (("name", "業者名", 120), ("load", "積載/台", 80), ("active", "状態", 70)):
            self.ctree.heading(k, text=t)
            self.ctree.column(k, width=w)
        self.ctree.pack(fill="x", pady=6)
        self.ctree.bind("<<TreeviewSelect>>", lambda e: self._load_carrier())
        tk.Label(carriers, text="業者名", font=f(13), bg=CARD, fg=MUTED).pack(anchor="w")
        self.cname = tk.Entry(carriers, font=f(16), relief="solid", bd=1)
        self.cname.pack(fill="x")
        r = tk.Frame(carriers, bg=CARD)
        r.pack(fill="x", pady=6)
        tk.Label(r, text="標準積載数", font=f(13), bg=CARD, fg=MUTED).pack(side="left")
        self.cload = 40
        self.cload_btn = button(r, "", self._edit_load, size=15, padx=10, pady=4)
        self.cload_btn.pack(side="right")
        self.cactive = tk.StringVar(value="1")
        Segmented(carriers, [("1", "有効"), ("0", "無効")], self.cactive, bg=CARD, size=14).pack(anchor="w")
        cb = tk.Frame(carriers, bg=CARD)
        cb.pack(fill="x", pady=(8, 0))
        button(cb, "保存", self.save_carrier, kind="primary", size=15).pack(side="left", expand=True, fill="x", padx=(0, 4))
        button(cb, "新規", self.new_carrier, size=15).pack(side="left", expand=True, fill="x", padx=(4, 0))
        self.carrier_id: int | None = None

        cal = card(self, "臨時休業日・臨時稼働日")
        cal.grid(row=0, column=2, sticky="nsew", padx=(8, 0))
        self.otree = ttk.Treeview(cal, columns=("date", "kind"), show="headings", height=8, selectmode="browse")
        self.otree.heading("date", text="日付")
        self.otree.heading("kind", text="種別")
        self.otree.column("date", width=120)
        self.otree.column("kind", width=120)
        self.otree.pack(fill="x", pady=6)
        button(cal, "臨時休業日を追加", lambda: self._add_override("closure"), size=15).pack(fill="x", pady=3)
        button(cal, "臨時稼働日を追加", lambda: self._add_override("workday"), size=15).pack(fill="x", pady=3)
        button(cal, "選択した日を削除", self._delete_override, kind="danger", size=15).pack(fill="x", pady=3)

    # 基本設定
    def refresh(self):
        st = self.app.repo.get_settings()
        for key, label, unit, *_ in self.FIELDS:
            self.value_buttons[key].configure(text=f"{_num_str(getattr(st, key))} {unit}")
        self.hw_var.set("1" if st.holiday_work_enabled else "0")
        self.hw_seg.refresh()

        self.ctree.delete(*self.ctree.get_children())
        for c in self.app.repo.list_carriers():
            self.ctree.insert("", "end", iid=str(c.id), values=(c.name, c.standard_load, "有効" if c.active else "無効"))
        self.cload_btn.configure(text=f"{self.cload} ベール")

        self.otree.delete(*self.otree.get_children())
        for d, kind in self.app.repo.list_overrides():
            self.otree.insert("", "end", iid=d.isoformat(), values=(fmt_date(d), "臨時休業日" if kind == "closure" else "臨時稼働日"))

    def update_setting(self, key: str, value):
        st = self.app.repo.get_settings()
        setattr(st, key, value)
        self.app.repo.save_settings(st)
        self.app.refresh()

    def _edit(self, key):
        _, label, unit, dec, lo, hi = next(x for x in self.FIELDS if x[0] == key)
        st = self.app.repo.get_settings()
        res = NumberDialog(self, label, initial=getattr(st, key), decimal=dec, info=f"単位: {unit}",
                           min_value=lo, max_value=hi).show()
        if res is not None:
            self.update_setting(key, float(res) if dec else int(res))

    def _set_hw(self, value):
        self.update_setting("holiday_work_enabled", value == "1")

    # 運搬業者
    def _load_carrier(self):
        sel = self.ctree.selection()
        if not sel:
            return
        c = next(c for c in self.app.repo.list_carriers() if c.id == int(sel[0]))
        self.carrier_id, self.cload = c.id, c.standard_load
        self.cname.delete(0, "end")
        self.cname.insert(0, c.name)
        self.cactive.set("1" if c.active else "0")
        for seg in _descendants(self):
            if isinstance(seg, Segmented) and seg.var is self.cactive:
                seg.refresh()
        self.cload_btn.configure(text=f"{self.cload} ベール")

    def _edit_load(self):
        res = NumberDialog(self, "標準積載数", initial=self.cload, info="1台当たりのベール数", min_value=1, max_value=999).show()
        if res is not None:
            self.cload = res
            self.cload_btn.configure(text=f"{self.cload} ベール")

    def new_carrier(self):
        self.carrier_id, self.cload = None, 40
        self.cname.delete(0, "end")
        self.ctree.selection_remove(self.ctree.selection())
        self.cload_btn.configure(text=f"{self.cload} ベール")

    def save_carrier(self):
        name = self.cname.get().strip()
        if not name:
            messagebox.showwarning("入力不足", "業者名を入力してください", parent=self)
            return
        self.app.repo.save_carrier(Carrier(name, self.cload, self.cactive.get() == "1", self.carrier_id))
        self.app.refresh()

    # カレンダー
    def add_override(self, date: dt.date, kind: str):
        self.app.repo.set_override(date, kind)
        self.app.refresh()

    def _add_override(self, kind):
        title = "臨時休業日を選択" if kind == "closure" else "臨時稼働日を選択"
        d = DateDialog(self, title, self.app.today, self.app.today, self.app.repo.get_overrides()).show()
        if d:
            self.add_override(d, kind)

    def _delete_override(self):
        sel = self.otree.selection()
        if sel:
            self.app.repo.delete_override(dt.date.fromisoformat(sel[0]))
            self.app.refresh()


# ---------------------------------------------------------------------------


def main(argv=None):
    p = argparse.ArgumentParser(description="ベール製造計画アプリ")
    p.add_argument("--db", help="データベースファイル（省略時は %%LOCALAPPDATA%%/BalePlanner）")
    p.add_argument("--demo", action="store_true", help="デモデータ入りの一時データベースで起動")
    p.add_argument("--today", help="今日の日付を指定（動作確認用） YYYY-MM-DD")
    p.add_argument("--fullscreen", action="store_true", help="全画面で起動（F11で切替）")
    args = p.parse_args(argv)

    try:  # 高DPIのタブレットで文字がぼやけないようにする
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    if args.demo:
        repo = Repository(":memory:")
        seed_demo(repo, today)
    else:
        repo = Repository(args.db or default_db_path())
    app = App(repo, today, fullscreen=args.fullscreen)
    app.mainloop()


if __name__ == "__main__":
    main()
