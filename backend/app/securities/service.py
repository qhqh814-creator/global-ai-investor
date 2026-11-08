"""Securities master data persistence (P1)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from .models import SecurityRecord


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def upsert_securities(conn: sqlite3.Connection, records: list[SecurityRecord]) -> int:
    if not records:
        return 0
    ts = now_iso()
    rows = [
        (
            r.code,
            r.exchange,
            r.board,
            r.security_type,
            r.name_zh,
            r.name_en,
            r.listing_date.isoformat() if r.listing_date else None,
            r.status,
            r.total_shares,
            r.float_shares,
            r.industry,
            r.source_id,
            ts,
            ts,
            json.dumps(r.raw, ensure_ascii=False),
        )
        for r in records
    ]
    with conn:
        conn.executemany(
            """
            INSERT INTO securities(
                code, exchange, board, security_type, name_zh, name_en, listing_date,
                status, total_shares, float_shares, industry, source_id,
                fetched_at, updated_at, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(code) DO UPDATE SET
                exchange=excluded.exchange,
                board=excluded.board,
                name_zh=excluded.name_zh,
                name_en=excluded.name_en,
                listing_date=COALESCE(excluded.listing_date, securities.listing_date),
                status=excluded.status,
                total_shares=COALESCE(excluded.total_shares, securities.total_shares),
                float_shares=COALESCE(excluded.float_shares, securities.float_shares),
                industry=COALESCE(excluded.industry, securities.industry),
                source_id=excluded.source_id,
                fetched_at=excluded.fetched_at,
                updated_at=excluded.updated_at,
                raw_json=excluded.raw_json
            """,
            rows,
        )
    return len(rows)


def stats(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        "SELECT exchange, board, COUNT(*) AS n FROM securities GROUP BY exchange, board ORDER BY exchange, board"
    ).fetchall()
    total = conn.execute("SELECT COUNT(*) AS n FROM securities").fetchone()["n"]
    return {"total": int(total), "by_exchange_board": [dict(r) for r in rows]}


def list_securities(conn: sqlite3.Connection, exchange: str | None = None, board: str | None = None, limit: int = 100) -> list[dict]:
    sql = "SELECT code, exchange, board, security_type, name_zh, name_en, listing_date, status, industry, source_id FROM securities WHERE 1=1"
    args: list = []
    if exchange:
        sql += " AND exchange = ?"
        args.append(exchange)
    if board:
        sql += " AND board = ?"
        args.append(board)
    sql += " ORDER BY code LIMIT ?"
    args.append(max(1, min(limit, 1000)))
    return [dict(r) for r in conn.execute(sql, args).fetchall()]
