"""稼働カレンダー（製造可能日・出荷可能日の判定）。"""
from __future__ import annotations

import datetime as dt

import jpholiday

from .models import CalendarOverrides


def is_second_saturday(d: dt.date) -> bool:
    """月の2回目の土曜日か（8〜14日の土曜日）。"""
    return d.weekday() == 5 and 8 <= d.day <= 14


def is_holiday(d: dt.date, overrides: CalendarOverrides | None = None) -> bool:
    """休業日か（日曜・第2土曜・祝日・臨時休業日。臨時稼働日は休業日にしない）。"""
    ov = overrides or CalendarOverrides()
    if d in ov.workdays:
        return False
    if d in ov.closures:
        return True
    return d.weekday() == 6 or is_second_saturday(d) or jpholiday.is_holiday(d)


def is_production_day(d: dt.date, overrides: CalendarOverrides | None = None) -> bool:
    """製造可能日（月〜土で休業日でない日）。"""
    return not is_holiday(d, overrides)


def is_shipping_day(d: dt.date, overrides: CalendarOverrides | None = None) -> bool:
    """出荷可能日（月〜金で休業日でない日。臨時稼働日は曜日に関係なく可）。"""
    ov = overrides or CalendarOverrides()
    if d in ov.workdays:
        return True
    return d.weekday() < 5 and not is_holiday(d, ov)
