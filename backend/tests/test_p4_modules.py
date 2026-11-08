from __future__ import annotations

import sqlite3

from backend.app.db.migrate import migrate
from backend.app.quotes.service import get_dashboard
from backend.app.screening.service import latest_run, run_screening
from backend.app.signals.service import list_signals, run_signals
from backend.app.watchlist.service import (
    add_item,
    ensure_default_watchlist,
    list_items,
    remove_item,
)

NOW = "2026-11-06T15:00:00+08:00"


def make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    migrate(conn)
    conn.executemany(
        "INSERT INTO securities(code, exchange, board, name_zh, source_id, fetched_at, updated_at) VALUES (?, ?, ?, ?, 'test', ?, ?)",
        [
            ("600000", "SSE", "MAIN", "浦发银行", NOW, NOW),
            ("000001", "SZSE", "MAIN", "平安银行", NOW, NOW),
        ],
    )
    conn.executemany(
        """
        INSERT INTO stock_quotes(code, name, exchange, board, last, change_pct, prev_close, amount,
            quote_time, source_id, quote_kind, is_realtime, license_status, commercial_ok, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'eastmoney_quote', 'snapshot_unknown', 0, 'unlicensed_third_party', 0, ?)
        """,
        [
            ("600000", "浦发银行", "SSE", "MAIN", 11.0, 6.0, 10.0, 3.0e9, NOW, NOW),
            ("000001", "平安银行", "SZSE", "MAIN", 9.4, -6.0, 10.0, 1.0e9, NOW, NOW),
        ],
    )
    conn.commit()
    return conn


def test_watchlist_crud():
    conn = make_db()
    wid = ensure_default_watchlist(conn)
    assert add_item(conn, wid, "600000", "银行") is True
    items = list_items(conn, wid)
    assert len(items) == 1
    assert items[0]["name_zh"] == "浦发银行"
    assert items[0]["last"] == 11.0
    assert add_item(conn, wid, "600000") is False  # dedupe
    assert remove_item(conn, wid, "600000") is True
    assert list_items(conn, wid) == []


def test_watchlist_rejects_unknown_security():
    conn = make_db()
    wid = ensure_default_watchlist(conn)
    try:
        add_item(conn, wid, "999999")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "not found" in str(exc)


def test_signals_run_and_dedupe():
    conn = make_db()
    result = run_signals(conn)
    assert result["inserted"] == 3  # 600000 up+amount, 000001 down
    assert len(list_signals(conn)) == 3
    again = run_signals(conn)
    assert again["inserted"] == 0


def test_screening_run_and_latest():
    conn = make_db()
    result = run_screening(conn, {"max_results": 10})
    assert result["count"] == 2
    latest = latest_run(conn)
    assert latest is not None
    assert len(latest["items"]) == 2
    filtered = run_screening(conn, {"pct_min": 5, "max_results": 10})
    assert filtered["count"] == 1


def test_dashboard_uses_local_modules():
    conn = make_db()
    wid = ensure_default_watchlist(conn)
    add_item(conn, wid, "600000")
    run_signals(conn)
    run_screening(conn)
    dash = get_dashboard(conn)
    cards = {c["key"]: c for c in dash["cards"]}
    assert cards["dashboard.good_news"]["status"] == "unavailable"
    assert cards["dashboard.risk_alerts"]["status"] == "available"
    assert "0" in cards["dashboard.risk_alerts"]["value"]
    assert cards["dashboard.ai_opportunities"]["status"] == "available"
    assert cards["dashboard.watchlist"]["status"] == "available"
    assert cards["dashboard.signals"]["status"] == "available"
    assert cards["dashboard.paper_account"]["status"] == "unavailable"
