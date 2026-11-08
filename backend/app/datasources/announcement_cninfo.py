"""巨潮资讯 announcements adapter (P2).

Verified 2026-11-08:
  POST http://www.cninfo.com.cn/new/hisAnnouncement/query
  fields: secCode, secName, announcementId, announcementTitle, announcementTime(ms),
          adjunctUrl (PDF path), adjunctSize, adjunctType, announcementType
Full PDF URL = http://static.cninfo.com.cn/ + adjunctUrl

License: page has a disclaimer only; internal use, do not redistribute PDFs.
"""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone

import httpx

from ..content.models import AnnouncementRecord

SOURCE_ID = "cninfo_announcement"
URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
STATIC_BASE = "http://static.cninfo.com.cn/"
TZ = timezone(timedelta(hours=8))
HEADERS = {
    "Referer": "http://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/notice",
    "X-Requested-With": "XMLHttpRequest",
    "User-Agent": "GlobalAIInvestor/0.1 (personal research)",
}


def _iso(ms: int | None) -> str | None:
    if not ms:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000, tz=TZ).isoformat(timespec="seconds")
    except (ValueError, OSError):
        return None


def parse_announcements(rows: list[dict]) -> list[AnnouncementRecord]:
    out: list[AnnouncementRecord] = []
    for row in rows:
        ann_id = str(row.get("announcementId") or "").strip()
        title = str(row.get("announcementTitle") or "").strip()
        if not ann_id or not title:
            continue
        adjunct = row.get("adjunctUrl") or ""
        out.append(
            AnnouncementRecord(
                announcement_id=ann_id,
                sec_code=(row.get("secCode") or None),
                sec_name=(row.get("secName") or None),
                title=title,
                published_at=_iso(row.get("announcementTime")),
                url=f"{STATIC_BASE}{adjunct}" if adjunct else None,
                file_url=f"{STATIC_BASE}{adjunct}" if adjunct else None,
                file_type=(row.get("adjunctType") or None),
                file_size_kb=int(row["adjunctSize"]) if row.get("adjunctSize") not in (None, "") else None,
                category=(row.get("announcementTypeName") or row.get("announcementType") or None),
                raw=row,
            )
        )
    return out


def _query_page(start: date, end: date, page: int, page_size: int) -> dict:
    body = {
        "pageNum": str(page),
        "pageSize": str(page_size),
        "column": "szse",
        "tabName": "fulltext",
        "stock": "",
        "seDate": f"{start.isoformat()}~{end.isoformat()}",
        "isHLtitle": "true",
    }
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        resp = client.post(URL, data=body, headers=HEADERS)
        resp.raise_for_status()
        return resp.json()


def fetch_announcements(
    start: date,
    end: date,
    page_size: int = 30,
    max_pages: int = 10,
    page_delay: float = 0.5,
) -> list[AnnouncementRecord]:
    records: list[AnnouncementRecord] = []
    total_pages = 1
    page = 1
    while page <= min(max_pages, total_pages):
        payload = _query_page(start, end, page, page_size)
        rows = payload.get("announcements") or []
        if not rows:
            classified = payload.get("classifiedAnnouncements") or []
            if classified:
                rows = classified[0]
        if not rows:
            break
        records.extend(parse_announcements(rows))
        total_pages = int(payload.get("totalpages") or payload.get("totalPages") or page)
        page += 1
        if page <= min(max_pages, total_pages):
            time.sleep(page_delay)
    return records
