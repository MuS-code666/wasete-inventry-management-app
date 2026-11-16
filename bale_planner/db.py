"""SQLite によるデータ保存（端末内・オフライン）。"""
from __future__ import annotations

import datetime as dt
import os
import sqlite3
from dataclasses import asdict, fields
from pathlib import Path

from .models import (
    CalendarOverrides,
    Carrier,
    Mode,
    ProductionLock,
    Settings,
    Shipment,
    Slot,
    StockReading,
    StockTiming,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS carriers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    standard_load INTEGER NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS calendar_overrides (
    date TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('closure', 'workday'))
);
CREATE TABLE IF NOT EXISTS shipments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    slot TEXT NOT NULL CHECK (slot IN ('AM', 'PM')),
    carrier_id INTEGER NOT NULL REFERENCES carriers(id),
    trucks INTEGER NOT NULL,
    quantity_override INTEGER
);
CREATE INDEX IF NOT EXISTS idx_shipments_date ON shipments(date);
CREATE TABLE IF NOT EXISTS stock_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    timing TEXT NOT NULL CHECK (timing IN ('start', 'end')),
    quantity INTEGER NOT NULL,
    recorded_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS production_locks (
    date TEXT NOT NULL,
    slot TEXT NOT NULL CHECK (slot IN ('AM', 'PM')),
    bales INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (date, slot)
);
"""

DEFAULT_CARRIERS = [("A社", 44), ("B社", 40), ("C社", 38)]


def default_db_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "BalePlanner" / "bale_planner.db"


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


class Repository:
    def __init__(self, path: str | Path = ":memory:"):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        if not self.conn.execute("SELECT 1 FROM carriers LIMIT 1").fetchone():
            self.conn.executemany("INSERT INTO carriers(name, standard_load) VALUES (?, ?)", DEFAULT_CARRIERS)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # ---- 設定 ----------------------------------------------------------------

    def get_settings(self) -> Settings:
        rows = {r["key"]: r["value"] for r in self.conn.execute("SELECT key, value FROM settings")}
        s = Settings()
        for f in fields(Settings):
            if f.name in rows:
                raw = rows[f.name]
                cur = getattr(s, f.name)
                if isinstance(cur, bool):
                    val = raw == "1"
                elif isinstance(cur, int):
                    val = int(float(raw))
                else:
                    val = float(raw)
                setattr(s, f.name, val)
        return s

    def save_settings(self, s: Settings) -> None:
        for k, v in asdict(s).items():
            value = ("1" if v else "0") if isinstance(v, bool) else str(v)
            self.conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)", (k, value))
        self.conn.commit()

    def get_mode(self) -> Mode:
        r = self.conn.execute("SELECT value FROM settings WHERE key = 'ui_mode'").fetchone()
        return Mode(r["value"]) if r else Mode.MIN

    def set_mode(self, mode: Mode) -> None:
        self.conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES ('ui_mode', ?)", (mode.value,))
        self.conn.commit()

    # ---- 運搬業者 ------------------------------------------------------------

    def list_carriers(self, active_only: bool = False) -> list[Carrier]:
        sql = "SELECT * FROM carriers" + (" WHERE active = 1" if active_only else "") + " ORDER BY id"
        return [Carrier(r["name"], r["standard_load"], bool(r["active"]), r["id"]) for r in self.conn.execute(sql)]

    def save_carrier(self, c: Carrier) -> Carrier:
        if c.id is None:
            cur = self.conn.execute(
                "INSERT INTO carriers(name, standard_load, active) VALUES (?, ?, ?)", (c.name, c.standard_load, int(c.active))
            )
            c.id = cur.lastrowid
        else:
            self.conn.execute(
                "UPDATE carriers SET name = ?, standard_load = ?, active = ? WHERE id = ?",
                (c.name, c.standard_load, int(c.active), c.id),
            )
        self.conn.commit()
        return c

    # ---- カレンダー ----------------------------------------------------------

    def get_overrides(self) -> CalendarOverrides:
        ov = CalendarOverrides()
        for r in self.conn.execute("SELECT date, kind FROM calendar_overrides"):
            d = dt.date.fromisoformat(r["date"])
            (ov.closures if r["kind"] == "closure" else ov.workdays).add(d)
        return ov

    def list_overrides(self) -> list[tuple[dt.date, str]]:
        return [
            (dt.date.fromisoformat(r["date"]), r["kind"])
            for r in self.conn.execute("SELECT date, kind FROM calendar_overrides ORDER BY date")
        ]

    def set_override(self, date: dt.date, kind: str) -> None:
        self.conn.execute("INSERT OR REPLACE INTO calendar_overrides(date, kind) VALUES (?, ?)", (date.isoformat(), kind))
        self.conn.commit()

    def delete_override(self, date: dt.date) -> None:
        self.conn.execute("DELETE FROM calendar_overrides WHERE date = ?", (date.isoformat(),))
        self.conn.commit()

    # ---- 出荷予定 ------------------------------------------------------------

    def list_shipments(self, start: dt.date | None = None, end: dt.date | None = None) -> list[Shipment]:
        carriers = {c.id: c for c in self.list_carriers()}
        sql, args = "SELECT * FROM shipments WHERE 1=1", []
        if start:
            sql += " AND date >= ?"
            args.append(start.isoformat())
        if end:
            sql += " AND date <= ?"
            args.append(end.isoformat())
        sql += " ORDER BY date, slot, id"
        return [
            Shipment(
                dt.date.fromisoformat(r["date"]),
                Slot(r["slot"]),
                carriers[r["carrier_id"]],
                r["trucks"],
                r["quantity_override"],
                r["id"],
            )
            for r in self.conn.execute(sql, args)
        ]

    def save_shipment(self, s: Shipment) -> Shipment:
        vals = (s.date.isoformat(), s.slot.value, s.carrier.id, s.trucks, s.quantity_override)
        if s.id is None:
            cur = self.conn.execute(
                "INSERT INTO shipments(date, slot, carrier_id, trucks, quantity_override) VALUES (?, ?, ?, ?, ?)", vals
            )
            s.id = cur.lastrowid
        else:
            self.conn.execute(
                "UPDATE shipments SET date = ?, slot = ?, carrier_id = ?, trucks = ?, quantity_override = ? WHERE id = ?",
                (*vals, s.id),
            )
        self.conn.commit()
        return s

    def delete_shipment(self, shipment_id: int) -> None:
        self.conn.execute("DELETE FROM shipments WHERE id = ?", (shipment_id,))
        self.conn.commit()

    # ---- 実在庫 --------------------------------------------------------------

    def add_stock_reading(self, r: StockReading) -> None:
        # 同じ日・同じタイミングの入力は上書き（入力ミスの訂正）
        self.conn.execute("DELETE FROM stock_readings WHERE date = ? AND timing = ?", (r.date.isoformat(), r.timing.value))
        self.conn.execute(
            "INSERT INTO stock_readings(date, timing, quantity, recorded_at) VALUES (?, ?, ?, ?)",
            (r.date.isoformat(), r.timing.value, r.quantity, _now()),
        )
        self.conn.commit()

    def list_stock_readings(self, limit: int = 30) -> list[StockReading]:
        rows = self.conn.execute(
            "SELECT * FROM stock_readings ORDER BY date DESC, CASE timing WHEN 'end' THEN 0 ELSE 1 END LIMIT ?", (limit,)
        ).fetchall()
        return [StockReading(dt.date.fromisoformat(r["date"]), StockTiming(r["timing"]), r["quantity"]) for r in rows]

    # ---- 製造数の手動確定 ----------------------------------------------------

    def list_locks(self) -> list[ProductionLock]:
        return [
            ProductionLock(dt.date.fromisoformat(r["date"]), Slot(r["slot"]), r["bales"])
            for r in self.conn.execute("SELECT * FROM production_locks ORDER BY date, slot")
        ]

    def set_lock(self, date: dt.date, slot: Slot, bales: int) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO production_locks(date, slot, bales, updated_at) VALUES (?, ?, ?, ?)",
            (date.isoformat(), slot.value, bales, _now()),
        )
        self.conn.commit()

    def clear_lock(self, date: dt.date, slot: Slot) -> None:
        self.conn.execute("DELETE FROM production_locks WHERE date = ? AND slot = ?", (date.isoformat(), slot.value))
        self.conn.commit()
