"""Content sync service (P2): announcements (cninfo) and RSS news."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta, timezone

from ..datasources.announcement_cninfo import SOURCE_ID as ANN_SOURCE_ID
from ..datasources.announcement_cninfo import fetch_announcements
from ..datasources.news_rss import SOURCES as NEWS_SOURCES
from ..datasources.news_rss import fetch_news

TZ = timezone(timedelta(hours=8))


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def _upsert_source(conn: sqlite3.Connection, source_id: str, name: str, kind: str, url: str, license_status: str, commercial_ok: int) -> None:
    with conn:
        conn.execute(
            """
            INSERT INTO data_sources(source_id, name, kind, base_url, license_status, commercial_ok, latency_class, enabled, config_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'minutes', 1, NULL, ?)
            ON CONFLICT(source_id) DO UPDATE SET
                name=excluded.name, kind=excluded.kind, base_url=excluded.base_url,
                license_status=excluded.license_status, commercial_ok=excluded.commercial_ok,
                updated_at=excluded.updated_at
            """,
            (source_id, name, kind, url, license_status, commercial_ok, now_iso()),
        )


def _availability(conn: sqlite3.Connection, key: str, status: str, reason: str | None) -> None:
    ts = now_iso()
    with conn:
        conn.execute(
            """
            INSERT INTO data_availability(data_key, status, reason_code, detail, last_success_at, updated_at)
            VALUES (?, ?, ?, NULL, ?, ?)
            ON CONFLICT(data_key) DO UPDATE SET
                status=excluded.status, reason_code=excluded.reason_code,
                last_success_at=CASE WHEN excluded.status='AVAILABLE' THEN excluded.last_success_at ELSE data_availability.last_success_at END,
                updated_at=excluded.updated_at
            """,
            (key, status, reason, ts if status == "AVAILABLE" else None, ts),
        )


def sync_announcements(
    conn: sqlite3.Connection,
    fetch_fn=fetch_announcements,
    days: int = 7,
    page_size: int = 30,
    max_pages: int = 10,
) -> dict:
    end = date.today()
    start = end - timedelta(days=days)
    fetched_at = now_iso()
    _upsert_source(conn, ANN_SOURCE_ID, "巨潮资讯公告", "announcement", "http://www.cninfo.com.cn/new/hisAnnouncement/query",
                   "public_page", 0)
    try:
        records = fetch_fn(start, end, page_size=page_size, max_pages=max_pages)
    except Exception as exc:  # noqa: BLE001
        _availability(conn, "content.announcements", "UNAVAILABLE", "upstream_error")
        return {"inserted": 0, "fetched": 0, "error": str(exc)}
    inserted = 0
    with conn:
        for r in records:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO announcements(
                    announcement_id, sec_code, sec_name, title, published_at, url, file_url,
                    file_type, file_size_kb, category, source_id, fetched_at, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    r.announcement_id, r.sec_code, r.sec_name, r.title, r.published_at,
                    r.url, r.file_url, r.file_type, r.file_size_kb, r.category,
                    r.source_id, fetched_at, json.dumps(r.raw or {}, ensure_ascii=False),
                ),
            )
            inserted += cur.rowcount
    _availability(conn, "content.announcements", "AVAILABLE", None)
    return {"inserted": inserted, "fetched": len(records), "error": None, "range": f"{start}~{end}"}


def sync_news(conn: sqlite3.Connection, fetch_fn=fetch_news) -> dict:
    fetched_at = now_iso()
    total_fetched = 0
    inserted = 0
    errors: list[str] = []
    for source_id, meta in NEWS_SOURCES.items():
        _upsert_source(conn, source_id, meta["name"], "news", meta["url"], meta["license_status"], 0)
        try:
            records = fetch_fn(source_id)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{source_id}: {exc}")
            continue
        total_fetched += len(records)
        with conn:
            for r in records:
                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO news_items(
                        source_id, title, url, summary, published_at, fetched_at, license_status, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (r.source_id, r.title, r.url, r.summary, r.published_at, fetched_at, r.license_status, None),
                )
                inserted += cur.rowcount
    status = "AVAILABLE" if total_fetched else "UNAVAILABLE"
    _availability(conn, "content.news", status, None if total_fetched else "upstream_error")
    return {"fetched": total_fetched, "inserted": inserted, "errors": errors}


def list_news(conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
    rows = conn.execute(
        "SELECT id, source_id, title, url, summary, published_at, fetched_at, license_status "
        "FROM news_items ORDER BY COALESCE(published_at, fetched_at) DESC LIMIT ?",
        (max(1, min(limit, 500)),),
    ).fetchall()
    return [dict(r) for r in rows]


def list_announcements(conn: sqlite3.Connection, sec_code: str | None = None, limit: int = 50) -> list[dict]:
    sql = "SELECT id, announcement_id, sec_code, sec_name, title, published_at, url, file_type, file_size_kb, category, source_id FROM announcements"
    args: list = []
    if sec_code:
        sql += " WHERE sec_code = ?"
        args.append(sec_code)
    sql += " ORDER BY COALESCE(published_at, fetched_at) DESC LIMIT ?"
    args.append(max(1, min(limit, 500)))
    return [dict(r) for r in conn.execute(sql, args).fetchall()]

def list_global_news(conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
    rows = conn.execute(
        "SELECT g.id, g.source_id, g.title, g.url, g.summary, g.published_at, g.language, g.keywords, "
        "g.license_status, v.source_authenticity, v.price_reaction "
        "FROM global_news g LEFT JOIN news_verification v "
        "ON v.target_type='global_news' AND v.target_id=g.id "
        "ORDER BY COALESCE(g.published_at,g.fetched_at) DESC, g.id DESC LIMIT ?",
        (max(1, min(limit, 200)),),
    ).fetchall()
    return [dict(r) for r in rows]
