from __future__ import annotations

import sqlite3
from datetime import date

from backend.app.content.models import AnnouncementRecord, NewsRecord
from backend.app.content.service import list_announcements, list_news, sync_announcements, sync_news
from backend.app.datasources.announcement_cninfo import parse_announcements
from backend.app.datasources.quote_tencent import parse_tencent
from backend.app.datasources.news_rss import parse_rss
from backend.app.db.migrate import migrate

CNINFO_ROWS = [
    {
        "secCode": "000001",
        "secName": "平安银行",
        "announcementId": "1225620612",
        "announcementTitle": "关联交易公告",
        "announcementTime": 1792771200000,
        "adjunctUrl": "finalpage/2026-10-24/1225620612.PDF",
        "adjunctSize": 169,
        "adjunctType": "PDF",
        "announcementType": "01010503",
        "announcementTypeName": "关联交易",
    },
    {
        "secCode": "600000",
        "secName": "浦发银行",
        "announcementId": "1225000001",
        "announcementTitle": "2026年第三季度报告",
        "announcementTime": 1792700000000,
        "adjunctUrl": "finalpage/2026-10-23/1225000001.PDF",
        "adjunctSize": 500,
        "adjunctType": "PDF",
        "announcementType": "010103",
        "announcementTypeName": "季度报告",
    },
]

RSS_XML = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel>
<item>
  <title><![CDATA[央行开展逆回购操作]]></title>
  <link>https://example.com/news/1</link>
  <description><![CDATA[<p>为维护银行体系流动性合理充裕，央行今日开展逆回购操作。</p>]]></description>
  <pubDate>Sat, 07 Nov 2026 10:00:00 +0800</pubDate>
</item>
<item>
  <title>超长标题测试</title>
  <link>https://example.com/news/2</link>
  <description>这是一段很长的摘要，用于验证摘要截断到一百个字符以内，避免存储全文。</description>
  <pubDate>Fri, 06 Nov 2026 09:00:00 +0800</pubDate>
</item>
</channel></rss>
"""

TENCENT_TEXT = (
    'v_sh000001="1~上证指数~000001~3649.18~3689.91~3612.15~477042561~0~0~0.00~0~0.00~0~0.00~0~0.00~0~0.00~0~0.00~0~0.00~0~0.00~0~0.00~0~0.00~0~~20261106161401~-40.73~-1.10~3660.49~3610.20~3649.18/477042561/772634566231~477042561~77263457~0.98~16.58~~3660.49~3610.20~1.36~573906.07~638979.91~0.00~-1~-1~0.86~0~3641.33~~~~~~77263456.6231~0.0000~0~ ~ZS~-8.05~1.39~~~~4258.86~3574.27~-1.12~-4.32~-6.44~48622641075"'
)


def make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    migrate(conn)
    return conn


def test_parse_cninfo_announcements():
    records = parse_announcements(CNINFO_ROWS)
    assert len(records) == 2
    first = records[0]
    assert first.announcement_id == "1225620612"
    assert first.file_url.startswith("http://static.cninfo.com.cn/finalpage/")
    assert first.published_at.startswith("2026-10-24")
    assert first.file_size_kb == 169


def test_parse_rss_and_summary_truncation():
    records = parse_rss(RSS_XML, "pbc_news", "public_page")
    assert len(records) == 2
    first = records[0]
    assert first.title == "央行开展逆回购操作"
    assert "<p>" not in (first.summary or "")
    assert first.published_at.startswith("2026-11-07")
    assert len(records[1].summary or "") <= 100


def test_sync_announcements_and_dedupe():
    conn = make_db()
    records = parse_announcements(CNINFO_ROWS)
    result = sync_announcements(conn, fetch_fn=lambda start, end, page_size, max_pages: records)
    assert result["inserted"] == 2
    result2 = sync_announcements(conn, fetch_fn=lambda start, end, page_size, max_pages: records)
    assert result2["inserted"] == 0
    items = list_announcements(conn, limit=10)
    assert len(items) == 2
    assert items[0]["file_type"] == "PDF"


def test_sync_news_and_dedupe():
    conn = make_db()
    pbc = parse_rss(RSS_XML, "pbc_news", "public_page")
    chinanews = parse_rss(RSS_XML, "chinanews_finance", "public_page")

    def fetch(source_id: str):
        return pbc if source_id == "pbc_news" else chinanews

    result = sync_news(conn, fetch_fn=fetch)
    assert result["fetched"] == 4
    assert result["inserted"] == 2  # same URLs across sources are deduped
    result2 = sync_news(conn, fetch_fn=fetch)
    assert result2["inserted"] == 0
    items = list_news(conn, limit=10)
    assert len(items) == 2
    row = conn.execute("SELECT status FROM data_availability WHERE data_key='content.news'").fetchone()
    assert row["status"] == "AVAILABLE"


def test_tencent_index_parse():
    quotes = parse_tencent(TENCENT_TEXT)
    assert len(quotes) == 1
    q = quotes[0]
    assert q.index_code == "000001"
    assert q.last == 3649.18
    assert q.change_pct == -1.10
    assert q.source_id == "tencent_quote"
    assert q.license_status == "unlicensed_third_party"
    assert q.is_realtime is False

def test_rss_gmt_date_and_relative_link():
    xml = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel>
<item>
  <title>央行新闻</title>
  <link>www.pbc.gov.cn/goutongjiaoliu/113456/113469/2026110516262373524/index.html</link>
  <description>示例摘要</description>
  <pubDate>4 Nov 2026 16:00:00 GMT</pubDate>
</item>
</channel></rss>
"""
    records = parse_rss(xml, "pbc_news", "public_page")
    assert len(records) == 1
    assert records[0].url.startswith("https://www.pbc.gov.cn/")
    assert records[0].published_at == "2026-11-05T00:00:00+08:00"
