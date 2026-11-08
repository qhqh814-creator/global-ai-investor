from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from backend.app.datasources.quote_eastmoney import parse_index_rows, parse_stock_rows
from backend.app.db.migrate import migrate
from backend.app.quotes.service import compute_breadth, get_dashboard, sync_quotes

INDEX_ROWS = [
    {"f2": 3649.18, "f3": -1.1, "f4": -40.73, "f12": "000001", "f13": 1, "f14": "上证指数", "f124": 1793952720},
    {"f2": 11175.78, "f3": -2.57, "f4": -295.31, "f12": "399001", "f13": 0, "f14": "深证成指", "f124": 1793952681},
    {"f2": 2465.23, "f3": -3.96, "f4": -101.57, "f12": "399006", "f13": 0, "f14": "创业板指", "f124": 1793952708},
    {"f2": 1253.2, "f3": -2.6, "f4": -33.48, "f12": "000688", "f13": 1, "f14": "科创50", "f124": 1793952702},
    {"f2": 888.48, "f3": -2.37, "f4": -21.59, "f12": "899050", "f13": 0, "f14": "北证50", "f124": 1793950364},
]

STOCK_ROWS = [
    {"f2": 11.0, "f3": 10.0, "f6": 1.0e8, "f12": "600000", "f13": 1, "f14": "浦发银行", "f18": 10.0, "f20": 1.0e11, "f124": 1793952720},
    {"f2": 11.0, "f3": 10.0, "f6": 2.0e8, "f12": "600001", "f13": 1, "f14": "ST某某", "f18": 10.0, "f20": 1.0e10, "f124": 1793952720},
    {"f2": 12.0, "f3": 20.0, "f6": 3.0e8, "f12": "300001", "f13": 0, "f14": "特锐德", "f18": 10.0, "f20": 1.0e10, "f124": 1793952720},
    {"f2": 8.0, "f3": -20.0, "f6": 4.0e8, "f12": "688001", "f13": 1, "f14": "华兴源创", "f18": 10.0, "f20": 1.0e10, "f124": 1793952720},
    {"f2": 13.0, "f3": 30.0, "f6": 5.0e8, "f12": "920085", "f13": 0, "f14": "森峰科技", "f18": 10.0, "f20": 1.0e9, "f124": 1793952720},
    {"f2": 10.0, "f3": 0.0, "f6": 6.0e8, "f12": "000001", "f13": 0, "f14": "平安银行", "f18": 10.0, "f20": 1.0e11, "f124": 1793952720},
    {"f2": "-", "f3": "-", "f6": 0, "f12": "600002", "f13": 1, "f14": "停牌股", "f18": 10.0, "f20": 1.0e9, "f124": 1793952720},
]


def make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    migrate(conn)
    return conn


def test_parse_indices():
    quotes = parse_index_rows(INDEX_ROWS)
    assert len(quotes) == 5
    by_code = {q.index_code: q for q in quotes}
    assert by_code["899050"].name == "北证50"
    assert by_code["000001"].is_realtime is False
    assert by_code["000001"].license_status == "unlicensed_third_party"
    assert by_code["000001"].quote_time.startswith("2026-11-06")


def test_parse_stocks_classification_and_suspended_filter():
    quotes = parse_stock_rows(STOCK_ROWS)
    by_code = {q.code: q for q in quotes}
    assert "600002" not in by_code  # suspended/no price must not be fabricated
    assert (by_code["600000"].exchange, by_code["600000"].board) == ("SSE", "MAIN")
    assert (by_code["300001"].exchange, by_code["300001"].board) == ("SZSE", "CHINEXT")
    assert (by_code["688001"].exchange, by_code["688001"].board) == ("SSE", "STAR")
    assert (by_code["920085"].exchange, by_code["920085"].board) == ("BSE", "BSE")


def test_compute_breadth_uses_rule_library():
    conn = make_db()
    stocks = parse_stock_rows(STOCK_ROWS)
    breadth = compute_breadth(conn, stocks, date(2026, 11, 8))
    assert breadth["up_count"] == 4
    assert breadth["down_count"] == 1
    assert breadth["flat_count"] == 1
    assert breadth["limit_up_count"] == 4
    assert breadth["limit_down_count"] == 1
    assert breadth["total_amount"] == pytest.approx(21.0e8)


def test_dashboard_without_data_all_unavailable():
    conn = make_db()
    dash = get_dashboard(conn)
    assert len(dash["cards"]) == 15
    assert all(c["status"] == "unavailable" for c in dash["cards"])
    assert all(c["value"] is None for c in dash["cards"])


def test_sync_and_dashboard_with_fake_sources():
    conn = make_db()
    summary = sync_quotes(
        conn,
        fetch_indices_fn=lambda: parse_index_rows(INDEX_ROWS),
        fetch_stocks_fn=lambda: parse_stock_rows(STOCK_ROWS),
    )
    assert summary["indices"] == 5
    assert summary["stocks"] == 6
    dash = get_dashboard(conn)
    cards = {c["key"]: c for c in dash["cards"]}
    assert cards["dashboard.sse_index"]["status"] == "available"
    assert "3,649.18" in cards["dashboard.sse_index"]["value"]
    assert cards["dashboard.sse_index"]["provenance"]["isRealtime"] is False
    assert cards["dashboard.limit_counts"]["status"] == "available"
    assert "涨停 4" in cards["dashboard.limit_counts"]["value"]
    assert cards["dashboard.ai_opportunities"]["status"] == "unavailable"


def test_sync_failure_marks_unavailable():
    conn = make_db()

    def fail():
        raise RuntimeError("upstream down")

    summary = sync_quotes(
        conn,
        fetch_indices_fn=fail,
        fetch_stocks_fn=fail,
        fetch_indices_fallback_fn=fail,
    )
    assert summary["errors"]
    dash = get_dashboard(conn)
    cards = {c["key"]: c for c in dash["cards"]}
    assert cards["dashboard.sse_index"]["status"] == "unavailable"
    row = conn.execute("SELECT status FROM data_availability WHERE data_key='dashboard.sse_index'").fetchone()
    assert row["status"] == "UNAVAILABLE"


def test_tencent_fallback_used_when_eastmoney_fails():
    conn = make_db()

    def fail():
        raise RuntimeError("eastmoney down")

    summary = sync_quotes(
        conn,
        fetch_indices_fn=fail,
        fetch_stocks_fn=lambda: [],
        fetch_indices_fallback_fn=lambda: parse_index_rows(INDEX_ROWS),
    )
    assert summary["indices"] == 5
    assert any("fallback" in e for e in summary["errors"])
    row = conn.execute("SELECT source_id, is_realtime FROM index_quotes LIMIT 1").fetchone()
    assert row["is_realtime"] == 0
    dash = get_dashboard(conn)
    cards = {c["key"]: c for c in dash["cards"]}
    assert cards["dashboard.sse_index"]["status"] == "available"

