"""Link news/announcements to listed companies (P3/P4).

Deterministic matching only: stock code mentioned in text, company short name
contained in text, or announcement's own sec_code. No LLM guessing; AI-provided
stock lists (when present) are still validated against the securities master.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))
CODE_RE = re.compile(r"(?<!\d)((?:60|68|00|30|43|83|87|88|92)\d{4})(?!\d)")


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def _securities_index(conn: sqlite3.Connection) -> tuple[dict[str, str], dict[str, str]]:
    by_code: dict[str, str] = {}
    by_name: dict[str, str] = {}
    for row in conn.execute("SELECT code, name_zh FROM securities"):
        code, name = row["code"], (row["name_zh"] or "").strip()
        by_code[code] = name
        if len(name) >= 2:
            by_name[name] = code
            # common prefix without ST/*ST for matching （仅补充，不覆盖原名）
            stripped = name.lstrip("*STst").strip()
            if len(stripped) >= 2 and stripped not in by_name:
                by_name[stripped] = code
    return by_code, by_name


def extract_links(conn: sqlite3.Connection, text: str, sec_code: str | None = None) -> list[tuple[str, str, float]]:
    by_code, by_name = _securities_index(conn)
    found: dict[str, tuple[str, float]] = {}
    if sec_code and sec_code in by_code:
        found[sec_code] = ("announcement_code", 1.0)
    for code in CODE_RE.findall(text or ""):
        if code in by_code and code not in found:
            found[code] = ("explicit_code", 0.95)
    for name, code in by_name.items():
        if name in (text or "") and code not in found:
            found[code] = ("company_name", 0.7)
    return [(code, match, conf) for code, (match, conf) in found.items()]


def sync_stock_links(conn: sqlite3.Connection) -> dict:
    """Rebuild derived links. Announcements link ONLY their own sec_code (the
    issuer); names of intermediaries (brokers/lawyers) must not become subjects."""
    ts = now_iso()
    inserted = 0
    by_code, _ = _securities_index(conn)
    with conn:
        conn.execute("DELETE FROM news_stock_links")
    news_rows = conn.execute("SELECT id, title, summary FROM news_items").fetchall()
    for row in news_rows:
        text = f"{row['title']} {row['summary'] or ''}"
        for code, match, conf in extract_links(conn, text):
            cur = conn.execute(
                "INSERT OR IGNORE INTO news_stock_links(target_type, target_id, code, match_type, confidence, created_at) "
                "VALUES ('news', ?, ?, ?, ?, ?)",
                (row["id"], code, match, conf, ts),
            )
            inserted += cur.rowcount
    ann_rows = conn.execute("SELECT id, sec_code FROM announcements").fetchall()
    for row in ann_rows:
        code = row["sec_code"]
        if code and code in by_code:
            cur = conn.execute(
                "INSERT OR IGNORE INTO news_stock_links(target_type, target_id, code, match_type, confidence, created_at) "
                "VALUES ('announcement', ?, ?, 'announcement_code', 1.0, ?)",
                (row["id"], code, ts),
            )
            inserted += cur.rowcount
    return {"inserted": inserted}


def links_for_analysis(conn: sqlite3.Connection, target_type: str, target_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT code, match_type, confidence FROM news_stock_links WHERE target_type=? AND target_id=? ORDER BY confidence DESC",
        (target_type, target_id),
    ).fetchall()
    return [dict(r) for r in rows]

