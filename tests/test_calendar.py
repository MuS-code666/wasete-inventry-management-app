import datetime as dt

from bale_planner.models import CalendarOverrides
from bale_planner.workcalendar import is_production_day, is_second_saturday, is_shipping_day


def d(m, day):
    return dt.date(2026, m, day)


def test_second_saturday():
    assert is_second_saturday(d(12, 12))
    assert not is_second_saturday(d(12, 5))
    assert not is_second_saturday(d(12, 19))


def test_weekday_rules():
    assert is_production_day(d(11, 16)) and is_shipping_day(d(11, 16))  # 月
    assert is_production_day(d(11, 21)) and not is_shipping_day(d(11, 21))  # 土
    assert not is_production_day(d(11, 22)) and not is_shipping_day(d(11, 22))  # 日
    assert not is_production_day(d(12, 12))  # 第2土曜


def test_national_holiday():
    assert not is_production_day(d(11, 23))  # 勤労感謝の日
    assert not is_shipping_day(d(11, 23))


def test_overrides():
    ov = CalendarOverrides(closures={d(11, 18)}, workdays={d(11, 22), d(11, 21)})
    assert not is_production_day(d(11, 18), ov)
    assert is_production_day(d(11, 22), ov) and is_shipping_day(d(11, 22), ov)
    assert is_shipping_day(d(11, 21), ov)  # 臨時稼働日は土曜でも出荷可
