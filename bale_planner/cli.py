"""試作確認用のコンソール出力。

使い方:
    python -m bale_planner.cli                 # 全シナリオを在庫最小化で表示
    python -m bale_planner.cli normal --mode max
    python -m bale_planner.cli normal --compare  # 両モードを並べて比較
    python -m bale_planner.cli normal --lock 2026-11-16:AM:20  # 手動変更して再計算
    python -m bale_planner.cli normal --csv out.csv
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import sys
import unicodedata

from .models import Mode, Plan, ProductionLock, Shipment, Slot, fmt_minutes
from .planner import build_plan
from .scenarios import SCENARIOS, Scenario

WEEKDAYS = "月火水木金土日"


def _w(text: str, width: int, right: bool = False) -> str:
    """全角文字を2桁として幅を揃える。"""
    n = sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in str(text))
    pad = " " * max(0, width - n)
    return pad + str(text) if right else str(text) + pad


def _ship_label(shipments: list[Shipment], date: dt.date, slot: Slot) -> str:
    items = [f"{s.carrier.name}{s.trucks}台" for s in shipments if s.date == date and s.slot is slot]
    return "+".join(items)


def _prod_label(production: int, minutes: int, holiday: bool, ot: int) -> str:
    if not production:
        return "-"
    tag = "休出" if holiday else (f"残{fmt_minutes(ot)}" if ot else "")
    return f"{production}({fmt_minutes(minutes)}{tag and ' ' + tag})"


def render(plan: Plan, scenario: Scenario) -> str:
    st = scenario.settings
    lines = [
        f"■ {scenario.title} ／ {plan.mode.label}",
        f"  起点在庫 {plan.start_inventory}  保管上限 {st.storage_cap}  能力 {st.bales_per_hour:g}ベール/時"
        + (f"  期間末目標 {st.target_end_inventory}" if plan.mode is Mode.MAX else "")
        + (f"  目標占有率 {st.target_occupancy_pct}%（{st.target_level()}）" if plan.mode is Mode.TARGET else ""),
        "  " + " | ".join([_w("日付", 10), _w("午前出荷", 26), _w("午前製造", 16), _w("午前末", 6),
                            _w("午後出荷", 26), _w("午後製造", 20), "終業在庫"]),
    ]
    for d in plan.days:
        am, pm = d.am, d.pm
        holiday = not am.production_day
        lines.append(
            "  "
            + " | ".join([
                _w(f"{d.date:%m/%d}({WEEKDAYS[d.date.weekday()]}){'*' if holiday else ''}", 10),
                _w(_fmt_ship(scenario, am), 26),
                _w(_prod_label(am.production, am.total_minutes, holiday, 0), 16),
                _w(am.inventory_end, 6, right=True),
                _w(_fmt_ship(scenario, pm), 26),
                _w(_prod_label(pm.production, pm.total_minutes, holiday, pm.overtime_minutes), 20),
                _w(pm.inventory_end, 8, right=True),
            ])
        )
    lines.append("  (* = 休業日。製造欄は ベール数(運転時間)、残=残業分、休出=休日出勤)")
    if plan.warnings:
        lines.append("  ▼ 警告・お知らせ")
        for w in plan.warnings:
            mark = "【要対応】" if w.level == "error" else "【お知らせ】"
            when = f"{w.date:%m/%d}" if w.date else ""
            if w.slot:
                when += f" {w.slot.label}"
            lines.append(f"   {mark}{when} {w.message}")
            for s in w.suggestions:
                lines.append(f"       → {s}")
    return "\n".join(lines)


def _fmt_ship(scenario: Scenario, sp) -> str:
    if not sp.shipment:
        return "-"
    label = f"{sp.shipment} {_ship_label(scenario.shipments, sp.date, sp.slot)}"
    if sp.shortage:
        label += f" 不足{sp.shortage}"
    return label


def write_csv(plan: Plan, path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["日付", "時間帯", "出荷予定", "出荷可能", "製造数", "通常(分)", "残業(分)", "休日出勤(分)", "終了時在庫", "手動確定"])
        for s in plan.slots:
            w.writerow([s.date, s.slot.label, s.shipment, s.shipped, s.production, s.regular_minutes,
                        s.overtime_minutes, s.holiday_minutes, s.inventory_end, "○" if s.locked else ""])


def _parse_lock(text: str) -> ProductionLock:
    date, slot, bales = text.split(":")
    return ProductionLock(dt.date.fromisoformat(date), Slot(slot.upper()), int(bales))


def main(argv: list[str] | None = None) -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    p = argparse.ArgumentParser(description="ベール製造計画の試算")
    p.add_argument("scenario", nargs="?", choices=list(SCENARIOS), help="省略時は全シナリオ")
    p.add_argument("--mode", choices=[m.value for m in Mode], default="min")
    p.add_argument("--compare", action="store_true", help="全モード（最小化・最大化・任意）を表示")
    p.add_argument("--lock", action="append", default=[], help="手動確定 YYYY-MM-DD:AM|PM:ベール数")
    p.add_argument("--csv", help="計画をCSVに出力")
    args = p.parse_args(argv)

    keys = [args.scenario] if args.scenario else list(SCENARIOS)
    modes = list(Mode) if args.compare else [Mode(args.mode)]
    for key in keys:
        sc = SCENARIOS[key]
        locks = sc.locks + [_parse_lock(x) for x in args.lock]
        for mode in modes:
            plan = build_plan(sc.readings, sc.shipments, sc.settings, mode, locks, sc.overrides)
            print(render(plan, sc))
            print()
            if args.csv:
                write_csv(plan, args.csv if len(modes) == 1 else args.csv.replace(".csv", f"_{mode.value}.csv"))


if __name__ == "__main__":
    main()
