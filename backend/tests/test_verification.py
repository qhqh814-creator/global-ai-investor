from __future__ import annotations

import sqlite3

from backend.app.content.global_news import parse_feed
from backend.app.content.verification import verify_content
from backend.app.db.migrate import migrate

NOW = "2026-11-08T20:00:00+08:00"


def make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    migrate(conn)
    conn.execute(
        "INSERT INTO securities(code,exchange,board,name_zh,source_id,fetched_at,updated_at) "
        "VALUES ('600000','SSE','MAIN','浦发银行','test',?,?)", (NOW, NOW)
    )
    return conn


def test_parse_rss_feed():
    xml = """<?xml version="1.0"?><rss version="2.0"><channel>
    <item><title>Company wins export order</title><link>https://example.com/1</link>
    <description>Big contract</description><pubDate>Sat, 08 Nov 2026 10:00:00 GMT</pubDate></item>
    </channel></rss>"""
    items = parse_feed(xml)
    assert len(items) == 1
    assert items[0]["title"] == "Company wins export order"
    assert items[0]["url"] == "https://example.com/1"


def test_official_announcement_and_price_reaction():
    conn = make_db()
    cur = conn.execute(
        "INSERT INTO announcements(announcement_id,sec_code,sec_name,title,published_at,url,source_id,fetched_at) "
        "VALUES ('A1','600000','浦发银行','获重大合同',?, 'https://example.com/a1','cninfo_announcement',?)",
        ("2026-11-05T08:00:00+08:00", NOW),
    )
    ann_id = cur.lastrowid
    conn.execute(
        "INSERT INTO news_stock_links(target_type,target_id,code,match_type,confidence,created_at) "
        "VALUES ('announcement',?,'600000','announcement_code',1.0,?)", (ann_id, NOW)
    )
    conn.executemany(
        "INSERT INTO kline_daily(code,trade_date,open,high,low,close,volume,amount,change_pct,adjust_type,source_id,fetched_at) "
        "VALUES ('600000',?,?,?,?,?,1000,1e7,?,'none','test',?)",
        [
            ("2026-11-04", 9.8, 10.0, 9.7, 9.9, 0.0, NOW),
            ("2026-11-05", 10.0, 10.3, 9.9, 10.2, 3.03, NOW),
        ],
    )
    conn.commit()
    verify_content(conn, limit=10)
    row = conn.execute("SELECT * FROM news_verification WHERE target_type='announcement' AND target_id=?", (ann_id,)).fetchone()
    assert row is not None
    assert row["source_authenticity"] == "OFFICIAL"
    assert row["price_reaction"] == "REACTED_UP"
    assert "600000" in row["stock_codes_json"]


def test_duplicate_titles_become_multi_source():
    conn = make_db()
    conn.executemany(
        "INSERT INTO news_items(source_id,title,url,summary,published_at,fetched_at,license_status) "
        "VALUES (?,?,?,?,?,?, 'public_page')",
        [
            ("chinanews_finance", "某公司获得重大出口订单", "https://example.com/n1", "", "2026-11-05T09:00:00+08:00", NOW),
            ("pbc_news", "某公司获得重大出口订单", "https://example.com/n2", "", "2026-11-05T09:10:00+08:00", NOW),
        ],
    )
    conn.commit()
    verify_content(conn, limit=10)
    rows = conn.execute("SELECT source_authenticity,corroboration_count FROM news_verification WHERE target_type='news'").fetchall()
    assert rows and all(r["source_authenticity"] == "MULTI_SOURCE" for r in rows)
    assert all(r["corroboration_count"] >= 2 for r in rows)
