import datetime as dt

from bale_planner.db import Repository
from bale_planner.models import Mode, Settings, Shipment, Slot, StockReading, StockTiming
from bale_planner.service import compute, seed_demo

TODAY = dt.date(2026, 11, 16)


def test_defaults_and_settings_roundtrip(tmp_path):
    path = tmp_path / "t.db"
    repo = Repository(path)
    assert [c.name for c in repo.list_carriers()] == ["A社", "B社", "C社"]
    assert repo.get_settings() == Settings()
    repo.save_settings(Settings(storage_cap=150, bales_per_hour=13.5, holiday_work_enabled=False))
    repo.set_mode(Mode.MAX)
    repo.close()

    repo = Repository(path)  # 再起動しても保持される
    st = repo.get_settings()
    assert st.storage_cap == 150 and st.bales_per_hour == 13.5 and st.holiday_work_enabled is False
    assert repo.get_mode() is Mode.MAX
    assert len(repo.list_carriers()) == 3  # 初期データは重複して入らない


def test_shipments_crud():
    repo = Repository()
    a = repo.list_carriers()[0]
    s = repo.save_shipment(Shipment(TODAY, Slot.AM, a, 2))
    assert repo.list_shipments()[0].quantity == 88
    s.quantity_override = 80
    repo.save_shipment(s)
    assert repo.list_shipments()[0].quantity == 80
    assert repo.list_shipments(TODAY + dt.timedelta(days=1)) == []
    repo.delete_shipment(s.id)
    assert repo.list_shipments() == []


def test_stock_reading_same_timing_overwrites():
    repo = Repository()
    repo.add_stock_reading(StockReading(TODAY, StockTiming.START, 40))
    repo.add_stock_reading(StockReading(TODAY, StockTiming.START, 42))
    repo.add_stock_reading(StockReading(TODAY, StockTiming.END, 50))
    readings = repo.list_stock_readings()
    assert [(r.timing, r.quantity) for r in readings] == [(StockTiming.END, 50), (StockTiming.START, 42)]


def test_overrides_and_locks():
    repo = Repository()
    repo.set_override(TODAY, "closure")
    repo.set_override(TODAY + dt.timedelta(days=6), "workday")
    ov = repo.get_overrides()
    assert TODAY in ov.closures and TODAY + dt.timedelta(days=6) in ov.workdays
    repo.delete_override(TODAY)
    assert TODAY not in repo.get_overrides().closures
    repo.set_lock(TODAY, Slot.PM, 30)
    repo.set_lock(TODAY, Slot.PM, 20)
    assert [(l.slot, l.bales) for l in repo.list_locks()] == [(Slot.PM, 20)]
    repo.clear_lock(TODAY, Slot.PM)
    assert repo.list_locks() == []


def test_compute_without_stock_returns_none():
    assert compute(Repository(), TODAY) is None


def test_compute_with_demo_and_lock():
    repo = Repository()
    seed_demo(repo, TODAY)
    view = compute(repo, TODAY)
    assert view.start == TODAY and view.stale_days == 0
    assert len(view.visible_days) == 14
    assert not view.plan.errors
    repo.set_lock(TODAY, Slot.AM, 38)
    after = compute(repo, TODAY)
    assert after.plan.day(TODAY).am.production == 38 and after.plan.day(TODAY).am.locked


def test_compute_extends_horizon_when_stock_is_old():
    repo = Repository()
    repo.add_stock_reading(StockReading(TODAY - dt.timedelta(days=3), StockTiming.START, 20))
    view = compute(repo, TODAY)
    assert view.stale_days == 3
    assert len(view.visible_days) == 14
    assert view.visible_days[0].date == TODAY


def test_end_of_day_reading_starts_tomorrow():
    repo = Repository()
    repo.add_stock_reading(StockReading(TODAY, StockTiming.END, 20))
    view = compute(repo, TODAY)
    assert view.start == TODAY + dt.timedelta(days=1)
    assert view.plan.start_inventory == 20
