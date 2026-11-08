from __future__ import annotations

import sqlite3
from datetime import date

from backend.app.datasources.szse_calendar import CalendarDay
from backend.app.db.migrate import migrate
from backend.app.trading_calendar import TradingCalendar


def fake_november_2026(year: int, month: int) -> list[CalendarDay]:
    assert (year, month) == (2026, 11)
    days: list[CalendarDay] = []
    for d in range(1, 31):
        day = date(2026, 11, d)
        trading = day.weekday() < 5  # no extra holidays in Nov 2026
        days.append(CalendarDay(trade_date=day, is_trading_day=trading))
    return days


def make_calendar() -> TradingCalendar:
    conn = sqlite3.connect(":memory:")
    migrate(conn)
    return TradingCalendar(conn)


def test_sync_month_and_is_trading_day():
    cal = make_calendar()
    assert cal.sync_month(2026, 11, fetch=fake_november_2026) == 30
    assert cal.is_trading_day(date(2026, 11, 6)) is True
    assert cal.is_trading_day(date(2026, 11, 7)) is False
    assert cal.is_trading_day(date(2026, 11, 8)) is False
    assert cal.is_trading_day(date(2026, 11, 9)) is True


def test_unknown_day_returns_none():
    cal = make_calendar()
    assert cal.is_trading_day(date(2026, 12, 1)) is None


def test_month_days_and_coverage():
    cal = make_calendar()
    cal.sync_month(2026, 11, fetch=fake_november_2026)
    rows = cal.month_days(2026, 11)
    assert len(rows) == 30
    assert all(r["source_id"] == "szse_calendar" for r in rows)
    coverage = cal.year_coverage(2026)
    assert coverage["days"] == 30
    # November 2026 has 21 weekdays
    assert coverage["trading_days"] == 21
