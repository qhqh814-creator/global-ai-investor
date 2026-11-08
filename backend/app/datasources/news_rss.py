"""RSS news adapters (P2).

Verified 2026-11-08:
- 中新网财经 RSS: https://www.chinanews.com.cn/rss/finance.xml (true RSS 2.0)
- 中国人民银行 RSS: https://www.pbc.gov.cn/goutongjiaoliu/113456/2986536/index.html (true RSS 2.0, content-type html)

News is stored as title + link + <=100 char summary only (copyright-safe).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

import httpx

from ..content.models import NewsRecord

TZ = timezone(timedelta(hours=8))
HEADERS = {"User-Agent": "GlobalAIInvestor/0.1 (personal research)"}

SOURCES: dict[str, dict] = {
    "chinanews_finance": {
        "name": "中新网财经",
        "url": "https://www.chinanews.com.cn/rss/finance.xml",
        "license_status": "public_page",
    },
    "pbc_news": {
        "name": "中国人民银行",
        "url": "https://www.pbc.gov.cn/goutongjiaoliu/113456/2986536/index.html",
        "license_status": "public_page",
    },
}

SUMMARY_LIMIT = 100


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _clean(text: str | None) -> str:
    if not text:
        return ""
    text = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", text, flags=re.S)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _truncate(text: str, limit: int = SUMMARY_LIMIT) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _published(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    # RFC822 with named zone: Python's %Z does not apply the offset, so handle
    # GMT/UTC explicitly to avoid shifting timestamps by the local timezone.
    for suffix in (" GMT", " UTC"):
        if value.upper().endswith(suffix):
            core = value[: -len(suffix)].strip()
            for fmt in ("%a, %d %b %Y %H:%M:%S", "%d %b %Y %H:%M:%S"):
                try:
                    dt = datetime.strptime(core, fmt).replace(tzinfo=timezone.utc)
                    return dt.astimezone(TZ).isoformat(timespec="seconds")
                except ValueError:
                    continue
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z", "%d %b %Y %H:%M:%S %z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=TZ)
            return dt.astimezone(TZ).isoformat(timespec="seconds")
        except ValueError:
            continue
    return None


def parse_rss(xml_text: str, source_id: str, license_status: str) -> list[NewsRecord]:
    root = ET.fromstring(xml_text)
    out: list[NewsRecord] = []
    for item in root.iter():
        if _local(item.tag) != "item":
            continue
        fields: dict[str, str] = {}
        for child in list(item):
            fields[_local(child.tag)] = (child.text or "").strip()
        title = _clean(fields.get("title"))
        link = (fields.get("link") or "").strip()
        if link and not link.lower().startswith("http"):
            link = "https://" + link.lstrip("/")
        if not title or not link:
            continue
        out.append(
            NewsRecord(
                source_id=source_id,
                title=title,
                url=link,
                summary=_truncate(_clean(fields.get("description"))) or None,
                published_at=_published(fields.get("pubdate") or fields.get("published")),
                license_status=license_status,
                raw=xml_text[:0],
            )
        )
    return out


def fetch_news(source_id: str) -> list[NewsRecord]:
    meta = SOURCES[source_id]
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        resp = client.get(meta["url"], headers=HEADERS)
        resp.raise_for_status()
        return parse_rss(resp.text, source_id, meta["license_status"])

