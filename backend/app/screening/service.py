"""Rule-based stock screening (P3/P4).

Only uses the latest real quote snapshot + securities master; never fabricates
rows. Results carry scoring reasons.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))

DEFAULT_FILTERS: dict = {
    "exclude_st": True,
    "min_amount": None,
    "pct_min": None,
    "pct_max": None,
    "max_results": 50,
}


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def run_screening(conn: sqlite3.Connection, filters: dict | None = None, name: str | None = None) -> dict:
    f = {**DEFAULT_FILTERS, **(filters or {})}
    rows = conn.execute(
        """
        SELECT q.code, q.name, q.exchange, q.board, q.last, q.change_pct, q.amount
        FROM stock_quotes q
        ORDER BY q.amount DESC
        """
    ).fetchall()
    results: list[dict] = []
    for row in rows:
        if f.get("exclude_st") and "ST" in (row["name"] or "").upper():
            continue
        if f.get("pct_min") is not None and (row["change_pct"] is None or row["change_pct"] < f["pct_min"]):
            continue
        if f.get("pct_max") is not None and (row["change_pct"] is None or row["change_pct"] > f["pct_max"]):
            continue
        if f.get("min_amount") is not None and (row["amount"] is None or row["amount"] < f["min_amount"]):
            continue
        reasons = [
            {"field": "change_pct", "value": row["change_pct"]},
            {"field": "amount", "value": row["amount"]},
        ]
        score = float(row["change_pct"] or 0) + (float(row["amount"] or 0) / 1e10)
        results.append({"code": row["code"], "score": score, "reasons": reasons})
        if len(results) >= int(f.get("max_results") or 50):
            break

    ts = now_iso()
    with conn:
        cur = conn.execute(
            "INSERT INTO screening_runs(name, filters_json, status, result_count, created_at) VALUES (?, ?, 'DONE', ?, ?)",
            (name, json.dumps(f, ensure_ascii=False), len(results), ts),
        )
        run_id = int(cur.lastrowid)
        conn.executemany(
            "INSERT INTO screening_results(run_id, code, score, reasons_json) VALUES (?, ?, ?, ?)",
            [(run_id, r["code"], r["score"], json.dumps(r["reasons"], ensure_ascii=False)) for r in results],
        )
    return {"run_id": run_id, "count": len(results), "filters": f}


def latest_run(conn: sqlite3.Connection) -> dict | None:
    run = conn.execute("SELECT * FROM screening_runs ORDER BY id DESC LIMIT 1").fetchone()
    if not run:
        return None
    items = conn.execute(
        """
        SELECT r.code, r.score, r.reasons_json, s.name_zh, q.last, q.change_pct
        FROM screening_results r
        LEFT JOIN securities s ON s.code = r.code
        LEFT JOIN stock_quotes q ON q.code = r.code
        WHERE r.run_id = ?
        ORDER BY r.score DESC
        """,
        (run["id"],),
    ).fetchall()
    return {
        "run": {k: run[k] for k in ("id", "name", "filters_json", "status", "result_count", "created_at")},
        "items": [dict(i) for i in items],
    }
