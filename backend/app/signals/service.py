"""Signal rules and evaluation against the latest quote snapshot (P4)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))

DEFAULT_RULES = [
    ("涨幅突破", "BUY", {"field": "change_pct", "op": ">=", "value": 5.0}),
    ("跌幅预警", "SELL", {"field": "change_pct", "op": "<=", "value": -5.0}),
    ("放量活跃", "BUY", {"field": "amount", "op": ">=", "value": 2_000_000_000}),
]


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def ensure_default_rules(conn: sqlite3.Connection) -> None:
    with conn:
        for name, side, condition in DEFAULT_RULES:
            conn.execute(
                "INSERT INTO signal_rules(name, side, condition_json, enabled, created_at) VALUES (?, ?, ?, 1, ?) "
                "ON CONFLICT(name) DO NOTHING",
                (name, side, json.dumps(condition, ensure_ascii=False), now_iso()),
            )


def _compare(value: float | None, op: str, target: float) -> bool:
    if value is None:
        return False
    return {
        ">=": value >= target,
        ">": value > target,
        "<=": value <= target,
        "<": value < target,
        "==": value == target,
    }.get(op, False)


def run_signals(conn: sqlite3.Connection) -> dict:
    ensure_default_rules(conn)
    rules = conn.execute("SELECT id, name, side, condition_json FROM signal_rules WHERE enabled = 1").fetchall()
    inserted = 0
    for rule in rules:
        cond = json.loads(rule["condition_json"])
        field = cond.get("field")
        op = cond.get("op", ">=")
        target = float(cond.get("value", 0))
        if field not in ("change_pct", "amount", "last"):
            continue
        rows = conn.execute(f"SELECT code, last, change_pct, amount, quote_time FROM stock_quotes WHERE {field} IS NOT NULL").fetchall()
        for row in rows:
            if not _compare(row[field], op, target):
                continue
            trade_date = (row["quote_time"] or "")[:10] or datetime.now(TZ).date().isoformat()
            with conn:
                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO signals(rule_id, code, side, trade_date, price, change_pct,
                        rule_version_id, evidence_json, triggered_at)
                    VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?)
                    """,
                    (
                        rule["id"], row["code"], rule["side"], trade_date, row["last"], row["change_pct"],
                        json.dumps({"rule": rule["name"], "condition": cond}, ensure_ascii=False),
                        now_iso(),
                    ),
                )
                inserted += cur.rowcount
    return {"rules": len(rules), "inserted": inserted}


def list_signals(conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
    rows = conn.execute(
        """
        SELECT s.id, s.code, s.side, s.trade_date, s.price, s.change_pct, s.triggered_at,
               r.name AS rule_name, sec.name_zh
        FROM signals s
        LEFT JOIN signal_rules r ON r.id = s.rule_id
        LEFT JOIN securities sec ON sec.code = s.code
        ORDER BY s.triggered_at DESC, s.id DESC LIMIT ?
        """,
        (max(1, min(limit, 500)),),
    ).fetchall()
    return [dict(r) for r in rows]
