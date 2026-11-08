"""Trading calendar service backed by SQLite.

Calendar data is sourced from the official SZSE month-list API (the only
official calendar endpoint verified working on 2026-11-08) and stored locally so
the app can run offline. Unknown dates return None - never assume a day is a
trading day.
"""

from __future__ import annotations

import sqlite3
from datetime import date

from ..datasources.szse_calendar import SOURCE_ID, CalendarDay, fetch_month


class TradingCalendar:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row

    def upsert_days(self, days: list[CalendarDay], source_id: str = SOURCE_ID) -> int:
        with self.conn:
            self.conn.executemany(
                """
                INSERT INTO trading_calendar(trade_date, is_trading_day, source_id, year, updated_at)
                VALUES (?, ?, ?, ?, datetime('now'))
                ON CONFLICT(trade_date) DO UPDATE SET
                    is_trading_day=excluded.is_trading_day,
                    source_id=excluded.source_id,
                    year=excluded.year,
                    updated_at=excluded.updated_at
                """,
                [(d.trade_date.isoformat(), 1 if d.is_trading_day else 0, source_id, d.trade_date.year) for d in days],
            )
        return len(days)

    def sync_month(self, year: int, month: int, fetch=fetch_month) -> int:
        return self.upsert_days(fetch(year, month))

    def sync_year(self, year: int, fetch=fetch_month) -> int:
        total = 0
        for month in range(1, 13):
            total += self.sync_month(year, month, fetch=fetch)
        return total

    def is_trading_day(self, day: date) -> bool | None:
        row = self.conn.execute(
            "SELECT is_trading_day FROM trading_calendar WHERE trade_date = ?", (day.isoformat(),)
        ).fetchone()
        if row is None:
            return None
        return bool(row["is_trading_day"])

    def month_days(self, year: int, month: int) -> list[dict]:
        prefix = f"{year:04d}-{month:02d}"
        rows = self.conn.execute(
            "SELECT trade_date, is_trading_day, source_id, updated_at FROM trading_calendar "
            "WHERE trade_date LIKE ? ORDER BY trade_date",
            (f"{prefix}%",),
        ).fetchall()
        return [dict(r) for r in rows]

    def year_coverage(self, year: int) -> dict:
        row = self.conn.execute(
            "SELECT COUNT(*) AS total, SUM(is_trading_day) AS trading FROM trading_calendar WHERE year = ?",
            (year,),
        ).fetchone()
        return {"year": year, "days": int(row["total"] or 0), "trading_days": int(row["trading"] or 0)}
