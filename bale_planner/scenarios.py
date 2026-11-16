"""試作用のダミーデータとテストシナリオ。

仮の前提: 製造能力 12 ベール/時 → 午前190分=38、午後220分=44、1日82ベール。
          残業上限60分（+12ベール）、保管上限130、期間末目標在庫60。
参考: 2026/11/23(月) は勤労感謝の日、2026/12/12 は第2土曜。
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from .models import CalendarOverrides, Carrier, ProductionLock, Settings, Shipment, Slot, StockReading, StockTiming

A = Carrier("A社", 44)
B = Carrier("B社", 40)
C = Carrier("C社", 38)
CARRIERS = [A, B, C]

AM, PM = Slot.AM, Slot.PM


def d(month: int, day: int) -> dt.date:
    return dt.date(2026, month, day)


@dataclass
class Scenario:
    key: str
    title: str
    readings: list[StockReading]
    shipments: list[Shipment]
    settings: Settings = field(default_factory=Settings)
    locks: list[ProductionLock] = field(default_factory=list)
    overrides: CalendarOverrides = field(default_factory=CalendarOverrides)


def _ship(date, slot, carrier, trucks, override=None):
    return Shipment(date, slot, carrier, trucks, override)


SCENARIOS: dict[str, Scenario] = {}


def _add(s: Scenario) -> None:
    SCENARIOS[s.key] = s


# 1. 通常の2週間（11/23 祝日を含む）
_add(
    Scenario(
        "normal",
        "通常の2週間",
        [StockReading(d(11, 16), StockTiming.START, 40)],
        [
            _ship(d(11, 16), PM, A, 1),
            _ship(d(11, 17), AM, B, 1),
            _ship(d(11, 18), PM, C, 1),
            _ship(d(11, 19), AM, A, 1),
            _ship(d(11, 20), PM, B, 1),
            _ship(d(11, 24), AM, A, 1),
            _ship(d(11, 25), PM, C, 1),
            _ship(d(11, 26), AM, B, 1),
            _ship(d(11, 27), PM, A, 1),
        ],
    )
)

# 2. 月曜午前の大口出荷（土曜製造分で間に合わせる）
_add(
    Scenario(
        "monday_big",
        "月曜午前に大口出荷（A社2台＋C社1台＝126）",
        [StockReading(d(11, 17), StockTiming.END, 10)],
        [_ship(d(11, 30), AM, A, 2), _ship(d(11, 30), AM, C, 1)],
    )
)

# 3. 休日を挟む出荷＋臨時休業日・臨時稼働日
_add(
    Scenario(
        "holiday",
        "連休明け出荷（11/20 臨時休業、11/22(日) 臨時稼働）",
        [StockReading(d(11, 16), StockTiming.START, 0)],
        [
            _ship(d(11, 19), PM, B, 1),
            _ship(d(11, 22), AM, C, 1),  # 臨時稼働日の日曜に出荷
            _ship(d(11, 24), AM, A, 2),  # 祝日明け火曜午前 → 期限は 11/22(日) まで
        ],
        overrides=CalendarOverrides(closures={d(11, 20)}, workdays={d(11, 22)}),
    )
)

# 4. 保管上限が厳しい（1便で上限を超える量を前日までに用意する必要がある）
_add(
    Scenario(
        "tight_storage",
        "保管上限が厳しい（月曜午前 A社3台＝132）",
        [StockReading(d(11, 18), StockTiming.START, 20)],
        [_ship(d(11, 30), AM, A, 3)],
    )
)

# 5. 残業が必要（翌朝の出荷に通常稼働だけでは足りない）
_add(
    Scenario(
        "overtime",
        "残業が必要（11/17 午前 A社2台＝88、在庫0）",
        [StockReading(d(11, 16), StockTiming.START, 0)],
        [_ship(d(11, 17), AM, A, 2)],
    )
)

# 6. 休日出勤が必要（祝日明けの大口出荷）
_add(
    Scenario(
        "holiday_work",
        "休日出勤が必要（11/24(火) 午前 A社2台＋C社1台＝126、11/21 始業在庫0）",
        [StockReading(d(11, 21), StockTiming.START, 0)],
        [_ship(d(11, 24), AM, A, 2), _ship(d(11, 24), AM, C, 1)],
    )
)

# 7. 出荷不足が避けられない
_add(
    Scenario(
        "shortage",
        "出荷不足（11/17 午前 A社2台＋B社1台＝128、在庫0）",
        [StockReading(d(11, 16), StockTiming.START, 0)],
        [_ship(d(11, 17), AM, A, 2), _ship(d(11, 17), AM, B, 1)],
    )
)
