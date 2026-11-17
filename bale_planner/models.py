"""データモデル（マスタ・日常入力・計画結果）。

すべて後から変更できる値として扱い、SQLite のテーブルにそのまま移せる形にしている。
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import Enum


class Slot(str, Enum):
    AM = "AM"
    PM = "PM"

    @property
    def label(self) -> str:
        return "午前" if self is Slot.AM else "午後"


class Mode(str, Enum):
    MIN = "min"  # 在庫最小化（後ろ倒し）
    MAX = "max"  # 在庫最大化（前倒し）
    TARGET = "target"  # 任意（指定した占有率を維持）

    @property
    def label(self) -> str:
        return {"min": "在庫最小化", "max": "在庫最大化", "target": "任意（占有率維持）"}[self.value]


class StockTiming(str, Enum):
    START = "start"  # 始業時
    END = "end"  # 終業時


@dataclass
class Settings:
    """基本マスタ。すべて設定画面から変更可能にする想定。"""

    storage_cap: int = 130  # 保管上限（出荷待ちを含む）
    bales_per_hour: float = 12.0  # 標準製造能力（仮）
    am_minutes: int = 190  # 午前の実質稼働時間 8:30-12:00 休憩20分
    pm_minutes: int = 220  # 午後の実質稼働時間 13:00-17:00 休憩20分
    overtime_max_minutes: int = 60  # 製造日の午後に追加できる残業時間の上限
    holiday_work_enabled: bool = True  # 休業日に休日出勤を自動で使うか
    target_end_inventory: int = 60  # 在庫最大化モードの期間末目標在庫
    target_occupancy_pct: int = 50  # 任意モードで維持する保管上限に対する占有率（%）
    plan_days: int = 14  # 計画期間

    def target_level(self) -> int:
        """任意モードで維持する在庫数（保管上限 × 目標占有率、切り捨て）。"""
        return self.storage_cap * max(0, min(100, self.target_occupancy_pct)) // 100

    def bales_for_minutes(self, minutes: int) -> int:
        """運転時間（分）で製造できるベール数（整数切り捨て）。"""
        return int(minutes * self.bales_per_hour // 60)

    def minutes_for_bales(self, bales: int) -> int:
        """指定ベール数の製造に必要な運転時間（分単位、切り上げ）。"""
        if bales <= 0:
            return 0
        return _ceil_div(bales * 60, self.bales_per_hour)


def fmt_minutes(minutes: int) -> str:
    """運転時間の表示用（計算は分単位のまま）。例: 130 → 2時間10分、60 → 1時間、20 → 20分。"""
    h, m = divmod(int(minutes), 60)
    if h and m:
        return f"{h}時間{m}分"
    if h:
        return f"{h}時間"
    return f"{m}分"


def _ceil_div(a: float, b: float) -> int:
    q = int(a // b)
    return q if q * b >= a else q + 1


@dataclass
class Carrier:
    """運搬業者マスタ。"""

    name: str
    standard_load: int  # 1台当たりのベール数
    active: bool = True
    id: int | None = None


@dataclass
class Shipment:
    """出荷予定（日付・時間帯・業者ごと）。"""

    date: dt.date
    slot: Slot
    carrier: Carrier
    trucks: int
    quantity_override: int | None = None  # 手動修正した出荷予定数
    id: int | None = None

    @property
    def quantity(self) -> int:
        if self.quantity_override is not None:
            return self.quantity_override
        return self.trucks * self.carrier.standard_load


@dataclass
class StockReading:
    """実在庫の入力（現場確認値を優先）。"""

    date: dt.date
    timing: StockTiming
    quantity: int


@dataclass
class ProductionLock:
    """作業員が手動で確定した製造予定数。再計算でも変更しない。"""

    date: dt.date
    slot: Slot
    bales: int


@dataclass
class CalendarOverrides:
    """臨時休業日・臨時稼働日。"""

    closures: set[dt.date] = field(default_factory=set)  # 臨時休業日
    workdays: set[dt.date] = field(default_factory=set)  # 臨時稼働日（製造・出荷とも可）


# ---- 計画結果 -------------------------------------------------------------


@dataclass
class SlotPlan:
    date: dt.date
    slot: Slot
    production_day: bool  # 通常の製造日か（False なら休日出勤枠）
    shipment: int  # 出荷予定数
    shipped: int  # 実際に出荷できる数（不足時は少なくなる）
    production: int  # 推奨製造数
    regular_minutes: int
    overtime_minutes: int
    holiday_minutes: int
    inventory_end: int  # 時間帯終了時の予測在庫
    locked: bool = False

    @property
    def total_minutes(self) -> int:
        return self.regular_minutes + self.overtime_minutes + self.holiday_minutes

    @property
    def shortage(self) -> int:
        return self.shipment - self.shipped


@dataclass
class Warning_:
    level: str  # "error"（対応必須） / "info"（残業・休日出勤の利用など）
    date: dt.date | None
    slot: Slot | None
    message: str
    suggestions: list[str] = field(default_factory=list)


@dataclass
class DayPlan:
    date: dt.date
    am: SlotPlan
    pm: SlotPlan

    @property
    def production(self) -> int:
        return self.am.production + self.pm.production

    @property
    def shipment(self) -> int:
        return self.am.shipment + self.pm.shipment

    @property
    def inventory_end(self) -> int:
        return self.pm.inventory_end


@dataclass
class Plan:
    mode: Mode
    start_inventory: int
    days: list[DayPlan]
    warnings: list[Warning_]

    @property
    def slots(self) -> list[SlotPlan]:
        return [s for d in self.days for s in (d.am, d.pm)]

    @property
    def errors(self) -> list[Warning_]:
        return [w for w in self.warnings if w.level == "error"]

    def day(self, date: dt.date) -> DayPlan:
        for d in self.days:
            if d.date == date:
                return d
        raise KeyError(date)
