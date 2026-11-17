"""画面の動作テスト（ダイアログを開かずに画面の処理を直接呼ぶ）。"""
import datetime as dt
import tkinter as tk

import pytest

from bale_planner.db import Repository
from bale_planner.models import Mode, Slot, StockTiming
from bale_planner.service import seed_demo

TODAY = dt.date(2026, 11, 16)


@pytest.fixture(scope="module")
def _app():
    # Windows の Tk は同一プロセスで作り直すと初期化に失敗することがあるため、1回だけ作る
    try:
        from bale_planner.app import App

        a = App(Repository(), TODAY)
    except tk.TclError as e:  # 画面のない環境
        pytest.skip(f"Tk を使えません: {e}")
    a.withdraw()
    yield a
    a.destroy()


@pytest.fixture
def app(_app):
    """テストごとに空のデータベースへ差し替える。"""
    _app.repo = Repository()
    _app.mode_var.set(Mode.MIN.value)
    _app.screens["ship"].new()
    _app.show("main")
    _app.refresh()
    return _app


def test_empty_db_shows_prompt(app):
    main = app.screens["main"]
    assert "実在庫がまだ入力されていません" in main.banner.cget("text")
    for name in app.screens:
        app.show(name)  # データなしでも全画面を表示できる


def test_stock_entry_and_production_change(app):
    seed_demo(app.repo, TODAY)
    app.refresh()
    main = app.screens["main"]
    assert main.target == TODAY
    assert "44 ベール" in main.prod_big.cget("text")
    assert main.start_big.cget("text") == "40 ベール"
    assert "始業時に入力" in main.start_detail.cget("text")
    assert "運転 3時間20分" in main.prod_pm.cget("text")  # 200分は時間表示
    assert "運転 20分" in main.prod_am.cget("text")
    assert str(main.btn_auto.cget("state")) == "disabled"

    app.set_production(TODAY, Slot.AM, 38)
    assert app.view.plan.day(TODAY).am.locked
    assert "手動" in main.prod_am.cget("text")
    assert str(main.btn_auto.cget("state")) == "normal"
    main._reset()
    assert not app.view.plan.day(TODAY).am.locked

    app.record_stock(StockTiming.END, 30)
    assert app.view.start == TODAY + dt.timedelta(days=1)
    assert "翌日" in main.day_label.cget("text")
    assert main.start_big.cget("text") == "30 ベール"
    assert "前日終業時に入力" in main.start_detail.cget("text")


def test_start_inventory_is_predicted_when_not_entered(app):
    from bale_planner.models import StockReading

    app.repo.add_stock_reading(StockReading(TODAY - dt.timedelta(days=1), StockTiming.START, 25))
    app.refresh()
    main = app.screens["main"]
    expected = app.view.plan.day(TODAY - dt.timedelta(days=1)).inventory_end
    assert main.start_big.cget("text") == f"{expected} ベール"
    assert "予測" in main.start_detail.cget("text")


def test_mode_switch_persists(app):
    seed_demo(app.repo, TODAY)
    app.mode_var.set(Mode.MAX.value)
    app.change_mode(Mode.MAX.value)
    assert app.view.plan.mode is Mode.MAX
    assert app.repo.get_mode() is Mode.MAX


def test_plan_screen_rows_and_lock(app):
    seed_demo(app.repo, TODAY)
    app.refresh()
    app.show("plan")
    scr = app.screens["plan"]
    rows = scr.tree.get_children()
    assert len(rows) == 14 and rows[0] == TODAY.isoformat()
    assert "holiday" in scr.tree.item("2026-11-23", "tags")  # 勤労感謝の日
    scr.tree.selection_set(rows[1])
    app.update()
    assert scr.selected_date() == TODAY + dt.timedelta(days=1)
    app.set_production(scr.selected_date(), Slot.PM, 0)
    assert "locked" in scr.tree.item(rows[1], "tags")
    assert scr.selected_date() == TODAY + dt.timedelta(days=1)  # 再計算後も選択を保持


def test_shipment_screen_add_edit_delete(app):
    app.repo.add_stock_reading(__import__("bale_planner.models", fromlist=["StockReading"]).StockReading(TODAY, StockTiming.START, 0))
    app.show("ship")
    scr = app.screens["ship"]
    scr.date = TODAY + dt.timedelta(days=1)
    scr.slot_var.set(Slot.AM.value)
    scr.carrier_var.set(str(app.repo.list_carriers()[1].id))  # B社
    scr._trucks(+1)
    scr.save()
    ships = app.repo.list_shipments()
    assert len(ships) == 1 and ships[0].quantity == 80
    assert app.view.plan.day(TODAY + dt.timedelta(days=1)).am.shipment == 80

    scr.override = 70
    scr.save()
    assert app.repo.list_shipments()[0].quantity == 70
    assert len(app.repo.list_shipments()) == 1  # 上書き保存

    scr.delete(confirm=False)
    assert app.repo.list_shipments() == []


def test_settings_screen(app):
    app.show("settings")
    scr = app.screens["settings"]
    scr.update_setting("storage_cap", 120)
    assert app.repo.get_settings().storage_cap == 120
    assert scr.value_buttons["storage_cap"].cget("text") == "120 ベール"
    scr._set_hw("0")
    assert app.repo.get_settings().holiday_work_enabled is False
    scr.add_override(TODAY + dt.timedelta(days=2), "closure")
    assert scr.otree.get_children() == ((TODAY + dt.timedelta(days=2)).isoformat(),)
    scr.cname.insert(0, "D社")
    scr.cload = 36
    scr.save_carrier()
    assert [c.name for c in app.repo.list_carriers()][-1] == "D社"


def test_number_dialog_logic(app):
    from bale_planner.app import NumberDialog

    d = NumberDialog(app, "テスト", initial=38, max_value=100)
    d.press("5")  # 最初の入力で初期値を置き換える
    d.press("2")
    assert d.text.get() == "52"
    d.press("⌫")
    d.press("9")
    d.press("9")
    d.press("9")
    d.ok()
    assert d.result is None and "範囲" in d.error.cget("text")
    d.press("C")
    d.press("7")
    d.ok()
    assert d.result == 7


def test_occupancy_rings(app):
    seed_demo(app.repo, TODAY)
    app.refresh()
    main = app.screens["main"]
    st = app.repo.get_settings()
    day = app.view.plan.day(TODAY)
    assert main.start_ring.pct == pytest.approx(40 / st.storage_cap * 100)
    assert main.end_ring.pct == pytest.approx(day.inventory_end / st.storage_cap * 100)
    assert main.start_ring.state == "normal"
    app.screens["settings"].update_setting("storage_cap", 45)  # 40/45 = 89% → 上限に近い
    app.show("main")
    assert main.start_ring.state == "warn"
    app.screens["settings"].update_setting("storage_cap", 30)  # 40/30 → 上限超過
    app.show("main")
    assert main.start_ring.state == "over"


def test_target_mode_in_ui(app):
    seed_demo(app.repo, TODAY)
    app.refresh()
    assert not app.target_btn.winfo_ismapped()
    app.mode_var.set(Mode.TARGET.value)
    app.change_mode(Mode.TARGET.value)
    app.deiconify()
    app.update()
    assert app.target_btn.winfo_ismapped()
    assert "目標 50%（65）" in app.target_btn.cget("text")
    app.set_target_occupancy(70)
    assert app.repo.get_settings().target_occupancy_pct == 70
    assert "目標 70%（91）" in app.target_btn.cget("text")
    assert app.view.plan.mode is Mode.TARGET
    assert app.view.plan.days[-1].inventory_end == 91
    app.mode_var.set(Mode.MIN.value)
    app.change_mode(Mode.MIN.value)
    app.update()
    assert not app.target_btn.winfo_ismapped()
    app.withdraw()
