"""Fallback securities-master population from the latest quote snapshot.

Use only when the official exchange list endpoint is unavailable (e.g. SZSE WAF
blocking). Every row is labeled `eastmoney_quote` / unlicensed third-party so it
can never be mistaken for an official exchange list.
"""

from __future__ import annotations

import json
import sqlite3

from .models import SecurityRecord
from .service import upsert_securities


def populate_from_quotes(conn: sqlite3.Connection, exchange: str = "SZSE") -> dict:
    rows = conn.execute(
        """
        SELECT q.code, q.name, q.exchange, q.board
        FROM stock_quotes q
        LEFT JOIN securities s ON s.code = q.code
        WHERE q.exchange = ? AND s.code IS NULL
        """,
        (exchange,),
    ).fetchall()
    records = [
        SecurityRecord(
            code=r["code"],
            exchange=r["exchange"],
            board=r["board"],
            name_zh=r["name"],
            source_id="eastmoney_quote",
            raw={"fallback": "quote_snapshot", "source_id": "eastmoney_quote"},
        )
        for r in rows
    ]
    inserted = upsert_securities(conn, records) if records else 0
    return {"exchange": exchange, "candidates": len(rows), "upserted": inserted, "source": "eastmoney_quote"}


def ensure_data_source(conn: sqlite3.Connection) -> None:
    from ..securities.service import now_iso

    with conn:
        conn.execute(
            """
            INSERT INTO data_sources(source_id, name, kind, base_url, license_status, commercial_ok, latency_class, enabled, config_json, updated_at)
            VALUES ('eastmoney_quote', '东方财富行情（证券主数据回退）', 'securities', 'https://push2.eastmoney.com/', 'unlicensed_third_party', 0, 'snapshot', 1, ?, ?)
            ON CONFLICT(source_id) DO UPDATE SET name=excluded.name, updated_at=excluded.updated_at
            """,
            (json.dumps({"note": "官方列表不可用时的回退来源；仅内测使用"}, ensure_ascii=False), now_iso()),
        )

