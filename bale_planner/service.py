"""画面とデータベースをつなぐ処理（計画の再計算・デモデータ）。"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, replace

from . import workcalendar as wc
from .db import Repository
from .models import Mode, Plan, Shipment, Slot, StockReading, StockTiming
from .planner import build_plan, resolve_start


@dataclass
class PlanView:
    plan: Plan
    shipments: list[Shipment]
    today: dt.date
    start: dt.date
    stale_days: int  # 実在庫の入力が何日前か（0 = 当日または前日終業時）
    start_source: StockTiming  # 起点にした実在庫が始業時・終業時のどちらの入力か

    @property
    def visible_days(self):
        """今日以降の日（2週間画面の表示対象）。"""
        return [d for d in self.plan.days if d.date >= self.today]


def compute(repo: Repository, today: dt.date, mode: Mode | None = None) -> PlanView | None:
    readings = repo.list_stock_readings()
    if not readings:
        return None
    settings = repo.get_settings()
    start, _ = resolve_start(readings)
    source = readings[0].timing  # 新しい順（同じ日は終業時が先）に並んでいる
    stale = max(0, (today - start).days)
    # 入力が古い場合も、今日から2週間先まで表示できるよう期間を延ばす
    settings = replace(settings, plan_days=settings.plan_days + stale)
    end = start + dt.timedelta(days=settings.plan_days - 1)
    shipments = repo.list_shipments(start, end)
    plan = build_plan(
        readings,
        shipments,
        settings,
        mode or repo.get_mode(),
        [l for l in repo.list_locks() if l.date >= start],
        repo.get_overrides(),
    )
    return PlanView(plan, shipments, today, start, stale, source)


def seed_demo(repo: Repository, today: dt.date) -> None:
    """動作確認用のデモデータ（今日から2週間分の出荷予定と実在庫）。"""
    carriers = repo.list_carriers(active_only=True)
    repo.add_stock_reading(StockReading(today, StockTiming.START, 40))
    ov = repo.get_overrides()
    pattern = [(Slot.PM, 0, 1), (Slot.AM, 1, 1), (Slot.PM, 2, 1), (Slot.AM, 0, 2), (Slot.PM, 1, 1)]
    n = 0
    d = today
    while d < today + dt.timedelta(days=14):
        if wc.is_shipping_day(d, ov):
            slot, ci, trucks = pattern[n % len(pattern)]
            repo.save_shipment(Shipment(d, slot, carriers[ci % len(carriers)], trucks))
            n += 1
        d += dt.timedelta(days=1)
