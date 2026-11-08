from __future__ import annotations

import json
import sqlite3

from backend.app.analysis.recommendations import (
    build_buy_candidates,
    build_position_advice,
    get_recommendation,
    list_recommendations,
    run_recommendations,
)
from backend.app.analysis.stock_links import sync_stock_links
from backend.app.db.migrate import migrate

NOW = "2026-11-08T20:00:00+08:00"
QUOTE_TIME = "2026-11-06T15:00:00+08:00"


def make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    migrate(conn)
    conn.executemany(
        "INSERT INTO securities(code, exchange, board, name_zh, source_id, fetched_at, updated_at) VALUES (?, ?, ?, ?, 'test', ?, ?)",
        [
            ("600000", "SSE", "MAIN", "浦发银行", NOW, NOW),
            ("000001", "SZSE", "MAIN", "平安银行", NOW, NOW),
            ("300001", "SZSE", "CHINEXT", "特锐德", NOW, NOW),
        ],
    )
    conn.executemany(
        """
        INSERT INTO stock_quotes(code, name, exchange, board, last, change_pct, prev_close, amount,
            quote_time, source_id, quote_kind, is_realtime, license_status, commercial_ok, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1e8, ?, 'eastmoney_quote', 'snapshot_unknown', 0, 'unlicensed_third_party', 0, ?)
        """,
        [
            ("600000", "浦发银行", "SSE", "MAIN", 10.0, 1.0, 9.9, QUOTE_TIME, NOW),
            ("000001", "平安银行", "SZSE", "MAIN", 9.0, -1.0, 9.1, QUOTE_TIME, NOW),
        ],
    )
    conn.commit()
    return conn


def add_news(conn: sqlite3.Connection, title: str, summary: str) -> int:
    cur = conn.execute(
        "INSERT INTO news_items(source_id, title, url, summary, published_at, fetched_at, license_status) "
        "VALUES ('chinanews_finance', ?, ?, ?, ?, ?, 'public_page')",
        (title, f"https://example.com/{abs(hash(title)) % 100000}", summary, NOW, NOW),
    )
    return int(cur.lastrowid)


def add_announcement(conn: sqlite3.Connection, sec_code: str, title: str) -> int:
    cur = conn.execute(
        "INSERT INTO announcements(announcement_id, sec_code, sec_name, title, published_at, url, source_id, fetched_at) "
        "VALUES (?, ?, '浦发银行', ?, ?, ?, 'cninfo_announcement', ?)",
        (str(abs(hash(title)) % 1000000), sec_code, title, NOW, "https://example.com/ann", NOW),
    )
    return int(cur.lastrowid)


def add_analysis(conn: sqlite3.Connection, target_type: str, target_id: int, sentiment: str, materiality: str, summary: str, quote: str) -> int:
    cur = conn.execute(
        """
        INSERT INTO ai_analysis(target_type, target_id, event_type, sentiment, materiality, summary,
            stocks_json, evidence_json, model_id, created_at)
        VALUES (?, ?, '重大合同', ?, ?, ?, '[]', ?, 'test-model', ?)
        """,
        (target_type, target_id, sentiment, materiality, summary,
         json.dumps([{"quote": quote, "source_url": "https://example.com/x", "published_at": NOW}], ensure_ascii=False),
         NOW),
    )
    return int(cur.lastrowid)


def add_position(conn: sqlite3.Connection, code: str, qty: int, avg_cost: float) -> None:
    conn.execute("INSERT INTO sim_accounts(name, initial_cash, cash, created_at) VALUES ('默认模拟账户', 1000000, 900000, ?)", (NOW,))
    account_id = conn.execute("SELECT id FROM sim_accounts LIMIT 1").fetchone()["id"]
    conn.execute(
        "INSERT INTO sim_positions(account_id, code, qty, sellable_qty, avg_cost, buy_date, updated_at) VALUES (?, ?, ?, 0, ?, '2026-11-01', ?)",
        (account_id, code, qty, avg_cost, NOW),
    )
    conn.commit()


def test_stock_links_from_name_code_and_announcement():
    conn = make_db()
    add_news(conn, "浦发银行获大额合同", "公司公告称获重大合同")
    add_news(conn, "市场异动", "关注 600000 与 300001 的走势")
    add_announcement(conn, "000001", "平安银行发布公告")
    conn.commit()
    result = sync_stock_links(conn)
    assert result["inserted"] >= 4
    rows = conn.execute("SELECT target_type, code, match_type FROM news_stock_links ORDER BY target_type, code").fetchall()
    assert any(r["code"] == "600000" and r["match_type"] == "company_name" for r in rows)
    assert any(r["code"] == "300001" and r["match_type"] == "explicit_code" for r in rows)
    assert any(r["code"] == "000001" and r["match_type"] == "announcement_code" for r in rows)


def test_buy_candidates_need_positive_analysis_with_evidence():
    conn = make_db()
    ann = add_announcement(conn, "600000", "浦发银行获重大合同")
    add_analysis(conn, "announcement", ann, "positive", "L3", "获重大合同，可能增厚业绩。", "获重大合同")
    conn.commit()
    run = run_recommendations(conn, model_id="test-model")
    assert run["stats"]["buy_candidates"] == 1
    items = list_recommendations(conn, reco_type="BUY")
    assert len(items) == 1
    item = items[0]
    assert item["code"] == "600000"
    assert item["action"] == "BUY_CANDIDATE"
    assert item["evidence"] and item["evidence"][0]["quotes"][0]["quote"] == "获重大合同"
    assert item["quote"]["is_realtime"] == 0


def test_negative_news_generates_sell_advice_for_holding():
    conn = make_db()
    add_position(conn, "600000", 1000, 10.5)
    news = add_news(conn, "浦发银行遭监管处罚", "公司收到监管处罚决定")
    add_analysis(conn, "news", news, "negative", "L3", "公司遭监管处罚，短期风险上升。", "公司收到监管处罚")
    conn.commit()
    run = run_recommendations(conn, model_id="test-model")
    assert run["stats"]["holding_advice"] == 1
    holdings = list_recommendations(conn, reco_type="HOLDING")
    assert len(holdings) == 1
    item = holdings[0]
    assert item["action"] in ("SELL", "REDUCE")
    assert item["position"]["qty"] == 1000
    assert any(r["type"] == "negative_news" for r in item["reasons"])
    assert item["evidence"][0]["quotes"][0]["quote"] == "公司收到监管处罚"


def test_holding_without_negative_evidence_is_hold_not_fake_sell():
    conn = make_db()
    add_position(conn, "600000", 1000, 10.5)
    conn.commit()
    run_recommendations(conn, model_id="test-model")
    holdings = list_recommendations(conn, reco_type="HOLDING")
    assert len(holdings) == 1
    item = holdings[0]
    assert item["action"] == "HOLD"
    assert any(r["type"] == "no_negative_evidence" for r in item["reasons"])
    assert item["evidence"] == []


def test_detail_and_no_fake_prices_without_quote():
    conn = make_db()
    # no quote for this code
    conn.execute("INSERT INTO securities(code, exchange, board, name_zh, source_id, fetched_at, updated_at) VALUES ('688001','SSE','STAR','华兴源创','test',?,?)", (NOW, NOW))
    add_position(conn, "688001", 100, 20.0)
    conn.commit()
    run_recommendations(conn, model_id="test-model")
    item = list_recommendations(conn, reco_type="HOLDING")[0]
    assert item["quote"] is None
    assert any(r["type"] == "quote_unavailable" for r in item["reasons"])
    detail = get_recommendation(conn, item["id"])
    assert detail and detail["reasons"]


def test_announcement_links_only_its_own_sec_code():
    conn = make_db()
    cur = conn.execute(
        "INSERT INTO announcements(announcement_id, sec_code, sec_name, title, published_at, url, source_id, fetched_at) "
        "VALUES ('A2', '600000', '浦发银行', '关于为平安银行股份有限公司提供担保的核查意见', ?, 'https://example.com/a2', 'cninfo_announcement', ?)",
        (NOW, NOW),
    )
    conn.commit()
    sync_stock_links(conn)
    links = conn.execute("SELECT code FROM news_stock_links WHERE target_type='announcement' AND target_id=?", (cur.lastrowid,)).fetchall()
    codes = {r["code"] for r in links}
    assert codes == {"600000"}  # 平安银行 is only an intermediary mention, not the issuer
