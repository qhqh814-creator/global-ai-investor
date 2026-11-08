from __future__ import annotations

import sqlite3

from backend.app.backtest.service import get_backtest, run_backtest
from backend.app.db.migrate import migrate
from backend.app.paper.service import get_account, place_order, reset_account
from backend.app.predictions.service import accuracy, create_prediction, settle_predictions

NOW = "2026-11-06T15:00:00+08:00"


def make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    migrate(conn)
    conn.execute(
        "INSERT INTO securities(code, exchange, board, name_zh, source_id, fetched_at, updated_at) "
        "VALUES ('600000', 'SSE', 'MAIN', '浦发银行', 'test', ?, ?)",
        (NOW, NOW),
    )
    conn.commit()
    return conn


def seed_kline(conn: sqlite3.Connection, code: str = "600000") -> None:
    rows = [
        ("2026-11-02", 9.8, 10.0, 9.9, 9.7, 0.0),
        ("2026-11-03", 10.0, 10.6, 10.7, 9.9, 6.0),
        ("2026-11-04", 10.7, 10.8, 10.9, 10.6, 1.9),
        ("2026-11-05", 10.8, 10.9, 11.0, 10.7, 0.9),
        ("2026-11-06", 11.0, 11.1, 11.2, 10.9, 1.8),
        ("2026-11-09", 11.2, 11.0, 11.3, 10.9, -0.9),
        ("2026-11-10", 11.0, 11.2, 11.3, 10.9, 1.8),
    ]
    conn.executemany(
        "INSERT INTO kline_daily(code, trade_date, open, high, low, close, volume, amount, change_pct, adjust_type, source_id, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 1000, 100000, ?, 'none', 'test', ?)",
        [(code, d, o, h, l, c, pct, NOW) for d, o, c, h, l, pct in rows],
    )
    conn.commit()


def seed_quote(conn: sqlite3.Connection, quote_time: str = NOW, last: float = 10.0) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO stock_quotes(code, name, exchange, board, last, change_pct, prev_close, amount,
            quote_time, source_id, quote_kind, is_realtime, license_status, commercial_ok, fetched_at)
        VALUES ('600000', '浦发银行', 'SSE', 'MAIN', ?, 0, ?, 1e9, ?, 'test', 'snapshot_unknown', 0,
                'unlicensed_third_party', 0, ?)
        """,
        (last, last, quote_time, NOW),
    )
    conn.commit()


def test_backtest_with_synthetic_bars():
    conn = make_db()
    seed_kline(conn)
    result = run_backtest(conn, ["600000"], "2026-11-02", "2026-11-10", entry_pct=5.0, hold_days=2)
    assert result["status"] == "DONE"
    assert result["metrics"]["trades_count"] == 2
    trades = result["trades"]
    sides = [t["side"] for t in trades]
    assert sides == ["BUY", "SELL"]
    assert trades[0]["rule_version_id"] == "SSE-2026.07.06"
    assert trades[1]["price"] > trades[0]["price"]
    assert result["metrics"]["total_return"] > 0
    stored = get_backtest(conn, result["backtest_id"])
    assert stored["metrics"]["trades_count"] == 2


def test_backtest_without_data_fails():
    conn = make_db()
    result = run_backtest(conn, ["600000"], "2026-01-01", "2026-02-01")
    assert result["status"] == "FAILED"


def test_paper_buy_sell_t1_flow():
    conn = make_db()
    seed_quote(conn, NOW, 10.0)
    buy = place_order(conn, "600000", "BUY", 100)
    assert buy["status"] == "FILLED"
    assert buy["rule_version_id"] == "SSE-2026.07.06"
    account = get_account(conn)
    assert account["positions"][0]["qty"] == 100
    assert account["positions"][0]["sellable_qty"] == 0
    assert account["account"]["cash"] < 1_000_000

    sell_same_day = place_order(conn, "600000", "SELL", 100)
    assert sell_same_day["status"] == "REJECTED"
    assert "T1_NOT_SELLABLE" in sell_same_day["reason"]

    seed_quote(conn, "2026-11-09T15:00:00+08:00", 10.5)
    sell = place_order(conn, "600000", "SELL", 100)
    assert sell["status"] == "FILLED"
    assert get_account(conn)["positions"] == []

    reset = reset_account(conn)
    assert reset["ok"] is True
    assert get_account(conn)["account"]["cash"] == 1_000_000


def test_paper_rejects_insufficient_cash():
    conn = make_db()
    seed_quote(conn, NOW, 10.0)
    result = place_order(conn, "600000", "BUY", 200_000)
    assert result["status"] == "REJECTED"
    assert "INSUFFICIENT_CASH" in result["reason"]


def test_predictions_settle_and_accuracy():
    conn = make_db()
    seed_quote(conn, "2026-11-02T15:00:00+08:00", 10.0)
    for d, c in [("2026-11-03", 10.2), ("2026-11-04", 10.4), ("2026-11-05", 10.6), ("2026-11-06", 10.5)]:
        conn.execute(
            "INSERT INTO kline_daily(code, trade_date, open, high, low, close, volume, amount, change_pct, adjust_type, source_id, fetched_at) "
            "VALUES ('600000', ?, ?, 0, 0, ?, 1000, 100000, 0, 'none', 'test', ?)",
            (d, c, c, NOW),
        )
    conn.commit()
    up = create_prediction(conn, "600000", "UP", horizon_days=3)
    down = create_prediction(conn, "600000", "DOWN", horizon_days=3)
    result = settle_predictions(conn)
    assert result["settled"] == 2
    stats = accuracy(conn)
    assert stats["total"] == 2
    assert stats["hit"] == 1
    assert stats["accuracy"] == 0.5
    assert up["start_date"] == "2026-11-02"
    assert down["status"] == "PENDING"
