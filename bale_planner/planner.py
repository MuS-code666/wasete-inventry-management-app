"""2週間の製造計画を計算するロジック。

計算モデル
----------
1日を「午前」「午後」の2つの時間帯（スロット）に分け、各スロット内の在庫は次の順で動く。

    前スロット在庫 → 出荷(−) → 製造(+) → スロット終了時在庫（ここで保管上限をチェック）

したがって「午前出荷は前の製造日まで」「午後出荷は当日午前まで」の期限は、
「出荷スロットより前のスロットで製造した分だけ出荷できる」という1つのルールで表せる。
休日を挟む場合も自動的に「さらに前の製造日」が期限になる。

製造枠の優先順位は 通常稼働 → 残業（製造日の午後のみ） → 休日出勤（休業日）。
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from . import workcalendar as wc
from .models import (
    CalendarOverrides,
    DayPlan,
    Mode,
    Plan,
    ProductionLock,
    Settings,
    Shipment,
    Slot,
    SlotPlan,
    StockReading,
    StockTiming,
    Warning_,
)

PM_END = dt.time(17, 0)


@dataclass
class _SlotInfo:
    date: dt.date
    slot: Slot
    production_day: bool
    shipping_day: bool
    reg_cap: int
    ot_cap: int
    hol_cap: int
    shipment: int
    shipments: list[Shipment]
    lock: int | None


def resolve_start(readings: list[StockReading]) -> tuple[dt.date, int]:
    """最新の実在庫入力から計画の起点日と起点在庫を決める。

    同じ日に始業時・終業時の両方があれば新しい終業時を優先する（二重計上を防ぐ）。
    終業時の入力なら翌日から計画する。
    """
    if not readings:
        raise ValueError("実在庫の入力がありません")
    order = {StockTiming.START: 0, StockTiming.END: 1}
    latest = max(readings, key=lambda r: (r.date, order[r.timing]))
    if latest.timing is StockTiming.END:
        return latest.date + dt.timedelta(days=1), latest.quantity
    return latest.date, latest.quantity


def build_plan(
    readings: list[StockReading],
    shipments: list[Shipment],
    settings: Settings | None = None,
    mode: Mode = Mode.MIN,
    locks: list[ProductionLock] | None = None,
    overrides: CalendarOverrides | None = None,
) -> Plan:
    """2週間の製造計画を作る。手動変更は locks で渡すと、それ以外を再計算する。"""
    st = settings or Settings()
    ov = overrides or CalendarOverrides()
    start, inv0 = resolve_start(readings)
    slots = _build_slots(start, st, ov, shipments, locks or [])
    warnings: list[Warning_] = []

    # 1) 製造しなければ間に合わない最小限の量（在庫最小化モードの解）
    lower = _minimum_schedule(slots, inv0)

    # 2) モード別の製造数
    if mode is Mode.MIN:
        production = lower
    else:
        production = _maximum_schedule(slots, inv0, lower, st, warnings)

    plan = _simulate(slots, inv0, production, st, mode, warnings)
    _add_usage_info(plan, st, warnings)
    _validate_inputs(slots, inv0, st, warnings)
    warnings.sort(key=lambda w: (w.level != "error", w.date or dt.date.min, w.slot.value if w.slot else ""))
    return plan


# ---------------------------------------------------------------------------


def _build_slots(start, st: Settings, ov, shipments, locks) -> list[_SlotInfo]:
    lock_map = {(l.date, l.slot): l.bales for l in locks}
    result = []
    for n in range(st.plan_days):
        d = start + dt.timedelta(days=n)
        prod = wc.is_production_day(d, ov)
        ship = wc.is_shipping_day(d, ov)
        for slot in (Slot.AM, Slot.PM):
            minutes = st.am_minutes if slot is Slot.AM else st.pm_minutes
            reg = st.bales_for_minutes(minutes) if prod else 0
            ot = 0
            if prod and slot is Slot.PM:
                ot = st.bales_for_minutes(minutes + st.overtime_max_minutes) - reg
            hol = st.bales_for_minutes(minutes) if (not prod and st.holiday_work_enabled) else 0
            sh = [s for s in shipments if s.date == d and s.slot is slot]
            result.append(
                _SlotInfo(d, slot, prod, ship, reg, ot, hol, sum(s.quantity for s in sh), sh, lock_map.get((d, slot)))
            )
    return result


def _net_demand(slots: list[_SlotInfo], inv0: int) -> list[int]:
    """起点在庫と手動確定分で賄えない出荷数（スロット別）。"""
    available = inv0
    net = []
    for s in slots:
        take = min(available, s.shipment)
        net.append(s.shipment - take)
        available -= take
        if s.lock is not None:
            available += s.lock
    return net


def _alap(demand: list[int], caps: list[int]) -> tuple[list[int], list[int]]:
    """期限に間に合う範囲で最も遅いスロットに製造を割り当てる。

    戻り値: (スロット別製造数, この枠で賄えなかった出荷数のスロット別内訳)
    """
    n = len(demand)
    prod = [0] * n
    pending = 0
    for i in range(n - 1, -1, -1):
        x = min(pending, caps[i])
        prod[i] = x
        pending -= x
        pending += demand[i]
    # 前から順に引き当てて、不足した出荷を特定する
    residual = [0] * n
    available = 0
    for i in range(n):
        take = min(available, demand[i])
        residual[i] = demand[i] - take
        available -= take
        available += prod[i]
    return prod, residual


def _minimum_schedule(slots: list[_SlotInfo], inv0: int) -> list[int]:
    demand = _net_demand(slots, inv0)
    production = [s.lock if s.lock is not None else 0 for s in slots]
    for tier in ("reg_cap", "ot_cap", "hol_cap"):
        caps = [0 if s.lock is not None else getattr(s, tier) for s in slots]
        prod, demand = _alap(demand, caps)
        production = [a + b for a, b in zip(production, prod)]
        if not any(demand):
            break
    return production


def _maximum_schedule(slots, inv0, lower, st: Settings, warnings) -> list[int]:
    """保管上限を守りつつ前倒しで製造し、期間末に目標在庫になるようにする。

    最小計画の累計（lower）を常に下回らないので、出荷期限は必ず守られる。
    前倒し分は通常稼働時間内だけで作り、残業・休日出勤は最小計画が必要とする分だけ使う。
    """
    target = min(st.target_end_inventory, st.storage_cap)
    # 最小計画でも出荷できない分（不足）は、前倒ししても出荷できないため製造目標から除く
    inv = inv0
    total_ship = 0
    for s, p in zip(slots, lower):
        shipped = min(inv, s.shipment)
        total_ship += shipped
        inv = inv - shipped + p
    total_prod = max(total_ship + target - inv0, sum(lower))
    future_locks = [0] * (len(slots) + 1)
    for i in range(len(slots) - 1, -1, -1):
        future_locks[i] = future_locks[i + 1] + (slots[i].lock or 0)

    production = []
    inv = inv0
    cum = 0
    lower_cum = 0
    for i, s in enumerate(slots):
        lower_cum += lower[i]
        inv -= min(inv, s.shipment)
        if s.lock is not None:
            p = s.lock
        else:
            room = max(0, st.storage_cap - inv)
            remaining = max(0, total_prod - cum - future_locks[i + 1])
            desired = min(s.reg_cap, room, remaining)
            p = max(desired, lower_cum - cum)
        production.append(p)
        cum += p
        inv += p

    end_inv = inv
    if end_inv < target:
        warnings.append(
            Warning_(
                "info",
                slots[-1].date,
                None,
                f"期間末の予測在庫 {end_inv} ベールは目標在庫 {target} ベールに届きません",
                ["目標在庫を見直す", "残業・休日出勤で追加製造する"],
            )
        )
    return production


def _simulate(slots, inv0, production, st: Settings, mode, warnings) -> Plan:
    inv = inv0
    plans: list[SlotPlan] = []
    for s, p in zip(slots, production):
        shipped = min(inv, s.shipment)
        inv = inv - shipped + p
        minutes = st.minutes_for_bales(p)
        if s.production_day:
            base = st.am_minutes if s.slot is Slot.AM else st.pm_minutes
            reg = min(minutes, base)
            ot, hol = minutes - reg, 0
        else:
            reg, ot, hol = 0, 0, minutes
        sp = SlotPlan(s.date, s.slot, s.production_day, s.shipment, shipped, p, reg, ot, hol, inv, s.lock is not None)
        plans.append(sp)

        if sp.shortage:
            warnings.append(_shortage_warning(s, sp, slots, st))
        if s.lock is not None:
            cap = s.reg_cap + s.ot_cap + s.hol_cap
            if s.lock > cap:
                warnings.append(
                    Warning_(
                        "error",
                        s.date,
                        s.slot,
                        f"手動確定の製造数 {s.lock} ベールが製造可能数 {cap} ベールを超えています",
                        ["製造数を見直す", "製造能力の設定を確認する"],
                    )
                )

    _add_overflow_warnings(plans, st, warnings)
    days = [DayPlan(plans[i].date, plans[i], plans[i + 1]) for i in range(0, len(plans), 2)]
    return Plan(mode, inv0, days, warnings)


def _add_overflow_warnings(plans: list[SlotPlan], st: Settings, warnings) -> None:
    """保管上限超過を、連続する期間ごとに1件の警告にまとめる。"""
    i = 0
    while i < len(plans):
        if plans[i].inventory_end <= st.storage_cap:
            i += 1
            continue
        j = i
        while j + 1 < len(plans) and plans[j + 1].inventory_end > st.storage_cap:
            j += 1
        run = plans[i : j + 1]
        peak = max(p.inventory_end for p in run)
        until = f"{run[-1].date:%m/%d} {run[-1].slot.label}終了時まで" if j > i else ""
        sugg = ["出荷の一部を前の日・時間帯へ前倒しする、または複数便に分割する", "保管上限の設定を見直す"]
        if any(p.locked for p in run):
            sugg.insert(0, "手動で確定した製造数を減らす")
        warnings.append(
            Warning_(
                "error",
                run[0].date,
                run[0].slot,
                f"予測在庫が保管上限 {st.storage_cap} を最大 {peak - st.storage_cap} ベール超過（最大 {peak}）"
                + (f"、{until}続く" if until else ""),
                sugg,
            )
        )
        i = j + 1


def _shortage_warning(s: _SlotInfo, sp: SlotPlan, slots, st: Settings) -> Warning_:
    short = sp.shortage
    need_min = st.minutes_for_bales(short)
    sugg = []
    idx = slots.index(s)
    later = next((x for x in slots[idx + 1 :] if x.shipping_day), None)
    if later:
        sugg.append(f"出荷を {later.date:%m/%d} {later.slot.label}以降に変更する")
    for sh in s.shipments:
        trucks = -(-short // sh.carrier.standard_load)
        if trucks <= sh.trucks:
            sugg.append(f"{sh.carrier.name}のトラックを {trucks} 台減らす（1台 {sh.carrier.standard_load} ベール）")
    sugg.append(f"残業上限を延長する（不足分の製造に約 {need_min} 分必要）")
    if not st.holiday_work_enabled:
        sugg.append("休日出勤を有効にする")
    return Warning_(
        "error",
        s.date,
        s.slot,
        f"{s.slot.label}出荷 {sp.shipment} ベールに対し {short} ベール不足",
        sugg,
    )


def _add_usage_info(plan: Plan, st: Settings, warnings) -> None:
    for d in plan.days:
        ot = d.pm.overtime_minutes
        if ot:
            end = (dt.datetime.combine(d.date, PM_END) + dt.timedelta(minutes=ot)).time()
            warnings.append(Warning_("info", d.date, Slot.PM, f"残業 {ot} 分（17:00〜{end:%H:%M}）を使用"))
        for sp in (d.am, d.pm):
            if sp.holiday_minutes:
                warnings.append(
                    Warning_("info", d.date, sp.slot, f"休日出勤 {sp.slot.label} {sp.holiday_minutes} 分を使用")
                )


def _validate_inputs(slots, inv0, st: Settings, warnings) -> None:
    if inv0 > st.storage_cap:
        warnings.append(
            Warning_("error", slots[0].date, None, f"起点在庫 {inv0} ベールが保管上限 {st.storage_cap} を超えています")
        )
    for s in slots:
        if s.shipment and not s.shipping_day:
            warnings.append(
                Warning_(
                    "error",
                    s.date,
                    s.slot,
                    "出荷できない日（休業日・土曜）に出荷予定が入っています",
                    ["出荷日を変更する", "臨時稼働日として登録する"],
                )
            )


def today_summary(plan: Plan, date: dt.date, shipments: list[Shipment]) -> dict:
    """メイン画面向け：当日の情報。"""
    d = plan.day(date)
    trucks = sum(s.trucks for s in shipments if s.date == date)
    return {
        "date": date,
        "shipment_bales": d.shipment,
        "production": d.production,
        "am_minutes": d.am.total_minutes,
        "pm_minutes": d.pm.total_minutes,
        "inventory_end": d.inventory_end,
        "warnings": [w for w in plan.warnings if w.date == date],
        "trucks": trucks,
    }
