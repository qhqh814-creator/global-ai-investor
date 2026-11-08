"""Prediction tracking and accuracy statistics (P5).

Predictions are created from the latest real quote; settlement uses daily
K-lines (no fabricated outcomes). Unsettled predictions stay PENDING.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def create_prediction(
    conn: sqlite3.Connection,
    code: str,
    direction: str,
    horizon_days: int = 5,
    confidence: float | None = None,
    model_id: str | None = None,
) -> dict:
    direction = direction.upper()
    if direction not in ("UP", "DOWN", "FLAT"):
        raise ValueError("direction must be UP/DOWN/FLAT")
    quote = conn.execute("SELECT last, quote_time FROM stock_quotes WHERE code = ?", (code,)).fetchone()
    if not quote or not quote["last"]:
        raise ValueError("quote unavailable")
    start_date = (quote["quote_time"] or "")[:10]
    ts = now_iso()
    with conn:
        cur = conn.execute(
            "INSERT INTO ai_predictions(code, direction, horizon_days, confidence, model_id, start_date, start_price, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)",
            (code, direction, horizon_days, confidence, model_id, start_date, float(quote["last"]), ts),
        )
    return {"id": int(cur.lastrowid), "code": code, "direction": direction, "start_date": start_date,
            "start_price": float(quote["last"]), "status": "PENDING"}


def settle_predictions(conn: sqlite3.Connection) -> dict:
    rows = conn.execute("SELECT * FROM ai_predictions WHERE status='PENDING'").fetchall()
    settled = 0
    for row in rows:
        bars = conn.execute(
            "SELECT trade_date, close FROM kline_daily WHERE code = ? AND trade_date > ? ORDER BY trade_date LIMIT ?",
            (row["code"], row["start_date"], row["horizon_days"]),
        ).fetchall()
        if len(bars) < row["horizon_days"]:
            continue
        end = bars[row["horizon_days"] - 1]
        change_pct = (end["close"] - row["start_price"]) / row["start_price"]
        if row["direction"] == "UP":
            hit = change_pct > 0
        elif row["direction"] == "DOWN":
            hit = change_pct < 0
        else:
            hit = abs(change_pct) < 0.005
        ts = now_iso()
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO prediction_results(prediction_id, settled_at, end_date, end_price, actual_change_pct, hit, error_pct) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (row["id"], ts, end["trade_date"], float(end["close"]), round(change_pct, 6), 1 if hit else 0, round(abs(change_pct), 6)),
            )
            conn.execute("UPDATE ai_predictions SET status='SETTLED' WHERE id=?", (row["id"],))
        settled += 1
    return {"pending": len(rows), "settled": settled}


def list_predictions(conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
    rows = conn.execute(
        """
        SELECT p.*, r.end_date, r.end_price, r.actual_change_pct, r.hit
        FROM ai_predictions p
        LEFT JOIN prediction_results r ON r.prediction_id = p.id
        ORDER BY p.id DESC LIMIT ?
        """,
        (max(1, min(limit, 500)),),
    ).fetchall()
    return [dict(r) for r in rows]


def accuracy(conn: sqlite3.Connection) -> dict:
    row = conn.execute(
        "SELECT COUNT(*) AS total, SUM(hit) AS hits, AVG(error_pct) AS avg_error FROM prediction_results"
    ).fetchone()
    total = int(row["total"] or 0)
    hits = int(row["hits"] or 0)
    by_model = conn.execute(
        """
        SELECT p.model_id, COUNT(*) AS total, SUM(r.hit) AS hits
        FROM prediction_results r JOIN ai_predictions p ON p.id = r.prediction_id
        GROUP BY p.model_id
        """
    ).fetchall()
    ts = now_iso()
    if total:
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO accuracy_stats(stat_date, scope, model_id, total, hit, accuracy, avg_error) "
                "VALUES (?, 'ALL', NULL, ?, ?, ?, ?)",
                (ts[:10], total, hits, hits / total, float(row["avg_error"] or 0)),
            )
    return {
        "total": total,
        "hit": hits,
        "accuracy": round(hits / total, 6) if total else None,
        "avg_error": round(float(row["avg_error"] or 0), 6) if total else None,
        "by_model": [{"model_id": r["model_id"], "total": r["total"], "hit": r["hits"],
                      "accuracy": round(r["hits"] / r["total"], 6) if r["total"] else None} for r in by_model],
    }
