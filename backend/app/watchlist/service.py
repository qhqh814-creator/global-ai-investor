"""Watchlist CRUD (P4)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))
DEFAULT_NAME = "我的观察池"


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def ensure_default_watchlist(conn: sqlite3.Connection) -> int:
    with conn:
        conn.execute(
            "INSERT INTO watchlist(name, created_at) VALUES (?, ?) ON CONFLICT(name) DO NOTHING",
            (DEFAULT_NAME, now_iso()),
        )
    row = conn.execute("SELECT id FROM watchlist WHERE name = ?", (DEFAULT_NAME,)).fetchone()
    return int(row["id"]) if row else 0


def list_watchlists(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT id, name, created_at FROM watchlist ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def list_items(conn: sqlite3.Connection, watchlist_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT i.code, i.note, i.added_at, s.name_zh, s.exchange, s.board,
               q.last, q.change_pct, q.quote_time
        FROM watchlist_items i
        LEFT JOIN securities s ON s.code = i.code
        LEFT JOIN stock_quotes q ON q.code = i.code
        WHERE i.watchlist_id = ?
        ORDER BY i.id
        """,
        (watchlist_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def add_item(conn: sqlite3.Connection, watchlist_id: int, code: str, note: str | None = None) -> bool:
    code = (code or "").strip()
    if not code:
        raise ValueError("code is required")
    exists = conn.execute("SELECT 1 FROM securities WHERE code = ?", (code,)).fetchone()
    if not exists:
        raise ValueError("security not found")
    with conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO watchlist_items(watchlist_id, code, note, added_at) VALUES (?, ?, ?, ?)",
            (watchlist_id, code, note, now_iso()),
        )
    return cur.rowcount > 0


def remove_item(conn: sqlite3.Connection, watchlist_id: int, code: str) -> bool:
    with conn:
        cur = conn.execute("DELETE FROM watchlist_items WHERE watchlist_id = ? AND code = ?", (watchlist_id, code))
    return cur.rowcount > 0
