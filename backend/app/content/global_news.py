"""Global public news collection (export orders / contracts / macro).

Only public RSS/HTML headlines + links are stored. Sources are labeled
public_page/unknown; nothing here is claimed as licensed real-time data.
"""

from __future__ import annotations

import json
import re
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import httpx

TZ = timezone(timedelta(hours=8))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# 公开源（已实测可访问）；不可访问的源不放入，避免假装接入
SOURCES = {
    "prnewswire": {
        "url": "https://www.prnewswire.com/rss/news-releases-list.rss",
        "name": "PR Newswire",
        "license": "public_page",
        "language": "en",
    },
    "google_news_export": {
        "url": "https://news.google.com/rss/search?q=" + quote_plus('"export order" OR "large order" OR "supply contract"') + "&hl=en-US&gl=US&ceid=US:en",
        "name": "Google News (export/order query)",
        "license": "unknown_aggregator",
        "language": "en",
    },
    "cnbc_world": {
        "url": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        "name": "CNBC World News",
        "license": "public_page",
        "language": "en",
    },
    "marketwatch": {
        "url": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
        "name": "MarketWatch Top Stories",
        "license": "public_page",
        "language": "en",
    },
    "un_news": {
        "url": "https://news.un.org/feed/subscribe/en/news/all/rss.xml",
        "name": "UN News",
        "license": "public_page",
        "language": "en",
    },
}

KEYWORDS = (
    "order", "orders", "contract", "contracts", "export", "exports", "shipment",
    "supply", "supplier", "purchase", "procurement", "tender", "award",
    "订单", "合同", "出口", "中标", "采购", "供货", "大单",
)

TAG_RE = re.compile(r"<[^>]+>")


def _clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", TAG_RE.sub(" ", text or "")).strip()


def _parse_time(value: str | None) -> str:
    if not value:
        return ""
    try:
        return parsedate_to_datetime(value).astimezone(TZ).isoformat(timespec="seconds")
    except (TypeError, ValueError):
        return ""


def parse_feed(xml_text: str, limit: int = 20) -> list[dict]:
    """Parse RSS 2.0 or Atom into items (title/url/summary/published)."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    items: list[dict] = []
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    nodes = root.findall(".//item") or root.findall(".//atom:entry", ns)
    for node in nodes[:limit]:
        title = _clean(node.findtext("title") or node.findtext("atom:title", namespaces=ns))
        link = (
            node.findtext("link")
            or node.findtext("atom:link[@rel='alternate']", namespaces=ns)
            or (node.find("atom:link", ns).get("href") if node.find("atom:link", ns) is not None else "")
        )
        if isinstance(link, str) and link.startswith("<"):
            link = _clean(link)
        summary = _clean(
            node.findtext("description")
            or node.findtext("atom:summary", namespaces=ns)
            or node.findtext("atom:content", namespaces=ns)
        )
        published = node.findtext("pubDate") or node.findtext("atom:updated", namespaces=ns)
        if not title or not link:
            continue
        items.append({"title": title, "url": link, "summary": summary,
                      "published_at": _parse_time(published)})
    return items


def relevant(item: dict) -> bool:
    text = f"{item.get('title') or ''} {item.get('summary') or ''}".lower()
    return any(k.lower() in text for k in KEYWORDS)


def sync_global_news(conn: sqlite3.Connection, timeout: float = 20.0) -> dict:
    ts = datetime.now(TZ).isoformat(timespec="seconds")
    inserted = 0
    fetched = 0
    errors: list[str] = []
    with httpx.Client(timeout=timeout, headers={"User-Agent": UA}, follow_redirects=True) as client:
        for source_id, meta in SOURCES.items():
            try:
                resp = client.get(meta["url"])
                resp.raise_for_status()
                items = parse_feed(resp.text)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{source_id}: {type(exc).__name__}: {exc}")
                continue
            fetched += len(items)
            for item in items:
                if not relevant(item):
                    continue
                with conn:
                    cur = conn.execute(
                        "INSERT OR IGNORE INTO global_news(source_id,title,url,summary,published_at,language,"
                        "keywords,license_status,fetched_at,raw_json) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (
                            source_id, item["title"][:400], item["url"], (item["summary"] or "")[:1000],
                            item["published_at"], meta["language"],
                            ",".join([k for k in KEYWORDS if k.lower() in f"{item['title']} {item['summary']}".lower()]),
                            meta["license"], ts, json.dumps(item, ensure_ascii=False),
                        ),
                    )
                inserted += cur.rowcount
    return {"fetched": fetched, "inserted": inserted, "errors": errors}
