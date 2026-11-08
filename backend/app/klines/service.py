"""Daily K-line persistence (P5)."""

from __future__ import annotations

import sqlite3
from datetime import date

from ..datasources.kline_eastmoney import SOURCE_ID, fetch_daily


def now_iso() -> str:
    from datetime import datetime, timezone, timedelta

    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def sync_daily(conn: sqlite3.Connection, codes: list[tuple[str, str]], start: date, end: date) -> dict:
    fetched = 0
    rows = 0
    errors: list[str] = []
    for code, exchange in codes:
        try:
            bars = fetch_daily(code, exchange, start, end)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{code}: {exc}")
            continue
        fetched += len(bars)
        ts = now_iso()
        with conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO kline_daily(code, trade_date, open, high, low, close, volume,
                    amount, change_pct, adjust_type, source_id, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'none', ?, ?)
                """,
                [
                    (b.code, b.trade_date, b.open, b.high, b.low, b.close, b.volume, b.amount,
                     b.change_pct, SOURCE_ID, ts)
                    for b in bars
                ],
            )
        rows += len(bars)
    return {"codes": len(codes), "bars": rows, "errors": errors}


def load_bars(conn: sqlite3.Connection, code: str, start: str | None = None, end: str | None = None) -> list[dict]:
    sql = "SELECT trade_date, open, high, low, close, volume, amount, change_pct FROM kline_daily WHERE code = ?"
    args: list = [code]
    if start:
        sql += " AND trade_date >= ?"
        args.append(start)
    if end:
        sql += " AND trade_date <= ?"
        args.append(end)
    sql += " ORDER BY trade_date"
    return [dict(r) for r in conn.execute(sql, args).fetchall()]


def available_codes(conn: sqlite3.Connection, min_bars: int = 20) -> list[str]:
    rows = conn.execute(
        "SELECT code, COUNT(*) AS n FROM kline_daily GROUP BY code HAVING n >= ? ORDER BY code", (min_bars,)
    ).fetchall()
    return [r["code"] for r in rows]
