import datetime as dt

import pytest

from bale_planner.models import Mode, ProductionLock, Settings, Slot, StockReading, StockTiming
from bale_planner.planner import build_plan, resolve_start, today_summary
from bale_planner.scenarios import SCENARIOS, A, d, _ship

AM, PM = Slot.AM, Slot.PM


def run(key, mode=Mode.MIN, locks=None, settings=None):
    sc = SCENARIOS[key]
    return build_plan(sc.readings, sc.shipments, settings or sc.settings, mode, (locks or []) + sc.locks, sc.overrides)


def slot(plan, date, s):
    day = plan.day(date)
    return day.am if s is AM else day.pm


# ---- 全シナリオ共通の不変条件 --------------------------------------------------

UNAVOIDABLE_OVERFLOW = {"tight_storage"}
UNAVOIDABLE_SHORTAGE = {"shortage"}


@pytest.mark.parametrize("key", list(SCENARIOS))
@pytest.mark.parametrize("mode", list(Mode))
def test_invariants(key, mode):
    st = SCENARIOS[key].settings
    plan = run(key, mode)
    for s in plan.slots:
        assert s.inventory_end >= 0
        assert s.production >= 0
        # 通常稼働の製造日は 残業上限以内、休業日は休日出勤のみ
        if s.production_day:
            limit = (st.am_minutes if s.slot is AM else st.pm_minutes) + (st.overtime_max_minutes if s.slot is PM else 0)
            assert s.total_minutes <= limit
            assert s.holiday_minutes == 0
            if s.slot is AM:
                assert s.overtime_minutes == 0
        else:
            assert s.regular_minutes == 0 and s.overtime_minutes == 0
        # 運転時間は製造数をまかなえる
        assert st.bales_for_minutes(s.total_minutes) >= s.production
    if key not in UNAVOIDABLE_OVERFLOW:
        assert max(s.inventory_end for s in plan.slots) <= st.storage_cap
    if key not in UNAVOIDABLE_SHORTAGE:
        assert all(s.shortage == 0 for s in plan.slots)


@pytest.mark.parametrize("key", list(SCENARIOS))
def test_max_mode_is_never_behind_min_mode(key):
    lo, hi = run(key, Mode.MIN), run(key, Mode.MAX)
    cum_lo = cum_hi = 0
    for a, b in zip(lo.slots, hi.slots):
        cum_lo += a.production
        cum_hi += b.production
        assert cum_hi >= cum_lo


@pytest.mark.parametrize("key", [k for k in SCENARIOS])
def test_max_mode_reaches_target(key):
    plan = run(key, Mode.MAX)
    assert plan.days[-1].inventory_end == SCENARIOS[key].settings.target_end_inventory


def test_min_mode_ends_empty_when_feasible():
    for key in ("normal", "monday_big", "holiday", "overtime", "holiday_work"):
        assert run(key, Mode.MIN).days[-1].inventory_end == 0


# ---- シナリオ別の期待値 --------------------------------------------------------


def test_monday_am_shipment_built_by_saturday():
    plan = run("monday_big")
    sat = plan.day(d(11, 28))
    assert sat.inventory_end == 126  # 土曜終業時に月曜午前分がそろう
    assert sat.production == 82  # 土曜はフル稼働
    assert slot(plan, d(11, 27), PM).production == 34  # 不足分を金曜午後に後ろ倒しで製造
    assert slot(plan, d(11, 30), AM).shortage == 0


def test_holiday_overrides():
    plan = run("holiday")
    assert plan.day(d(11, 20)).production == 0  # 臨時休業日
    sun = plan.day(d(11, 22))  # 臨時稼働日
    assert sun.am.production_day and sun.am.shipped == 38
    assert sun.inventory_end == 88  # 祝日明け火曜午前の88ベールは日曜までに製造
    assert plan.day(d(11, 23)).production == 0


def test_overtime_used_only_when_needed():
    plan = run("overtime")
    pm = slot(plan, d(11, 16), PM)
    assert pm.production == 50 and pm.overtime_minutes == 30
    assert any("残業 30 分" in w.message for w in plan.warnings)
    assert not plan.errors
    # 通常シナリオでは残業しない
    assert all(s.overtime_minutes == 0 for s in run("normal").slots)


def test_holiday_work_used_after_overtime():
    plan = run("holiday_work")
    assert slot(plan, d(11, 21), PM).overtime_minutes == 60
    hol = slot(plan, d(11, 23), PM)
    assert hol.production == 32 and hol.holiday_minutes == 160
    assert not plan.errors


def test_holiday_work_disabled_gives_shortage_with_suggestion():
    plan = run("holiday_work", settings=Settings(holiday_work_enabled=False))
    am = slot(plan, d(11, 24), AM)
    assert am.shortage == 32
    err = plan.errors[0]
    assert "32 ベール不足" in err.message
    assert "休日出勤を有効にする" in err.suggestions


def test_shortage_warning_and_suggestions():
    plan = run("shortage")
    am = slot(plan, d(11, 17), AM)
    assert am.shipped == 94 and am.shortage == 34
    err = plan.errors[0]
    assert err.date == d(11, 17) and err.slot is AM
    assert any("11/17 午後以降" in s for s in err.suggestions)
    assert any("A社のトラックを 1 台減らす" in s for s in err.suggestions)
    assert any("約 170 分" in s for s in err.suggestions)


def test_storage_overflow_warning_grouped():
    plan = run("tight_storage")
    errs = plan.errors
    assert len(errs) == 1
    assert errs[0].date == d(11, 28) and "最大 2 ベール超過" in errs[0].message


def test_storage_cap_is_configurable():
    plan = run("tight_storage", settings=Settings(storage_cap=140))
    assert not plan.errors
    plan = run("normal", Mode.MAX, settings=Settings(storage_cap=100))
    assert max(s.inventory_end for s in plan.slots) <= 100


# ---- 手動変更と再計算 ----------------------------------------------------------


def test_manual_lock_recalculates_following_days():
    base = run("normal")
    locks = [ProductionLock(d(11, 16), AM, 38), ProductionLock(d(11, 16), PM, 44)]
    plan = run("normal", locks=locks)
    assert slot(plan, d(11, 16), AM).production == 38 and slot(plan, d(11, 16), AM).locked
    # 前倒しした分、翌日以降の製造が減る
    later = lambda p: sum(s.production for s in p.slots if s.date > d(11, 16))
    assert later(plan) < later(base)
    assert sum(s.production for s in plan.slots) == sum(s.production for s in base.slots)
    assert not plan.errors


def test_manual_lock_too_small_creates_shortage_warning():
    plan = run("overtime", locks=[ProductionLock(d(11, 16), PM, 10)])
    assert slot(plan, d(11, 17), AM).shortage > 0
    assert plan.errors


def test_manual_lock_over_capacity_is_flagged():
    plan = run("normal", locks=[ProductionLock(d(11, 16), AM, 100)])
    assert any("製造可能数" in w.message for w in plan.errors)


# ---- 実在庫の起点 --------------------------------------------------------------


def test_resolve_start_prefers_latest_end_of_day():
    readings = [
        StockReading(d(11, 16), StockTiming.START, 40),
        StockReading(d(11, 16), StockTiming.END, 55),
    ]
    assert resolve_start(readings) == (d(11, 17), 55)
    readings.append(StockReading(d(11, 17), StockTiming.START, 50))
    assert resolve_start(readings) == (d(11, 17), 50)


def test_shipment_quantity_override_and_non_shipping_day():
    ships = [_ship(d(11, 17), AM, A, 1, override=30), _ship(d(11, 21), AM, A, 1)]  # 11/21 は土曜
    plan = build_plan([StockReading(d(11, 16), StockTiming.START, 0)], ships)
    assert slot(plan, d(11, 17), AM).shipment == 30
    assert any("出荷できない日" in w.message for w in plan.errors)


def test_today_summary():
    sc = SCENARIOS["normal"]
    plan = run("normal")
    s = today_summary(plan, d(11, 16), sc.shipments)
    assert s["trucks"] == 1 and s["shipment_bales"] == 44
    assert s["production"] == 44 and s["inventory_end"] == 40
