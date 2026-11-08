"""Verify news authenticity proxy and price association.

We never claim to prove truth. We record: source class, independent
corroboration, and whether the linked stock actually reacted around the
publication time. A fact can be real but unrelated to price; that must be
visible, not hidden.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher

TZ = timezone(timedelta(hours=8))
PUNCT_RE = re.compile(r"[\s\W_]+", re.UNICODE)


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def _norm(title: str) -> str:
    return PUNCT_RE.sub("", (title or "").lower())[:120]


def _similar(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    return SequenceMatcher(None, a, b).ratio() >= 0.82


def _links(conn: sqlite3.Connection, target_type: str, target_id: int) -> list[str]:
    if target_type == "global_news":
        return []
    rows = conn.execute(
        "SELECT code FROM news_stock_links WHERE target_type=? AND target_id=?", (target_type, target_id)
    ).fetchall()
    return [r["code"] for r in rows]


def _price_reaction(conn: sqlite3.Connection, codes: list[str], published_at: str | None) -> tuple[str, list[dict]]:
    if not codes:
        return "NO_STOCK_LINK", []
    day = (published_at or "")[:10]
    if not day:
        return "NO_PRICE_DATA", []
    details: list[dict] = []
    labels: list[str] = []
    for code in codes[:5]:
        rows = conn.execute(
            "SELECT trade_date, close, change_pct FROM kline_daily WHERE code=? AND trade_date BETWEEN date(?, '-7 day') "
            "AND date(?, '+5 day') ORDER BY trade_date",
            (code, day, day),
        ).fetchall()
        if not rows:
            labels.append("NO_PRICE_DATA")
            continue
        event_idx = next((i for i, r in enumerate(rows) if r["trade_date"] >= day), None)
        if event_idx is None or event_idx == 0:
            labels.append("NO_PRICE_DATA")
            continue
        prev = rows[event_idx - 1]
        event = rows[event_idx]
        prev_pct = prev["change_pct"]
        event_pct = event["change_pct"]
        if prev_pct is None:
            prev_pct = (prev["close"] / rows[event_idx - 2]["close"] - 1) * 100 if event_idx >= 2 and rows[event_idx - 2]["close"] else None
        label = "NO_REACTION"
        if prev_pct is not None and prev_pct >= 5:
            label = "MOVED_BEFORE"
        elif event_pct is not None and event_pct >= 2:
            label = "REACTED_UP"
        elif event_pct is not None and event_pct <= -2:
            label = "REACTED_DOWN"
        labels.append(label)
        details.append({"code": code, "prev_pct": prev_pct, "event_date": event["trade_date"],
                        "event_pct": event_pct, "label": label})
    priority = ["MOVED_BEFORE", "REACTED_UP", "REACTED_DOWN", "NO_REACTION", "NO_PRICE_DATA"]
    reaction = next((p for p in priority if p in labels), "NO_PRICE_DATA")
    return reaction, details


def verify_content(conn: sqlite3.Connection, limit: int = 300) -> dict:
    """Rebuild verification rows for recent domestic news/announcements and global news."""
    targets: list[dict] = []
    for row in conn.execute(
        "SELECT id,source_id,title,url,published_at FROM news_items ORDER BY COALESCE(published_at,fetched_at) DESC LIMIT ?",
        (limit,),
    ):
        targets.append({"target_type": "news", **dict(row)})
    for row in conn.execute(
        "SELECT id,source_id,title,url,published_at FROM announcements ORDER BY COALESCE(published_at,fetched_at) DESC LIMIT ?",
        (limit,),
    ):
        targets.append({"target_type": "announcement", **dict(row)})
    for row in conn.execute(
        "SELECT id,source_id,title,url,published_at FROM global_news ORDER BY COALESCE(published_at,fetched_at) DESC LIMIT ?",
        (limit,),
    ):
        targets.append({"target_type": "global_news", **dict(row)})

    norms = [(_norm(t["title"]), t["source_id"], t["target_type"], t["id"]) for t in targets]
    verified = 0
    reacted = 0
    for target in targets:
        title_norm = _norm(target["title"])
        corroboration = 1
        for other_norm, other_source, other_type, other_id in norms:
            if (other_type, other_id) == (target["target_type"], target["id"]):
                continue
            if other_source != target["source_id"] and _similar(title_norm, other_norm):
                corroboration += 1
        if target["target_type"] == "announcement":
            source_class = "OFFICIAL"
        elif target["target_type"] == "global_news":
            source_class = "PUBLIC_GLOBAL"
        else:
            source_class = "PUBLIC_SINGLE"
        if corroboration >= 2:
            source_class = "MULTI_SOURCE"
        if not target.get("url") or not (target.get("title") or "").strip():
            source_class = "UNVERIFIED"
        codes = _links(conn, target["target_type"], target["id"])
        reaction, detail = _price_reaction(conn, codes, target.get("published_at"))
        if reaction.startswith("REACTED") or reaction == "MOVED_BEFORE":
            reacted += 1
        with conn:
            conn.execute(
                "INSERT INTO news_verification(target_type,target_id,source_authenticity,corroboration_count,"
                "price_reaction,price_detail_json,stock_codes_json,verified_at) VALUES (?,?,?,?,?,?,?,?) "
                "ON CONFLICT(target_type,target_id) DO UPDATE SET source_authenticity=excluded.source_authenticity,"
                "corroboration_count=excluded.corroboration_count,price_reaction=excluded.price_reaction,"
                "price_detail_json=excluded.price_detail_json,stock_codes_json=excluded.stock_codes_json,"
                "verified_at=excluded.verified_at",
                (target["target_type"], target["id"], source_class, min(corroboration, 5), reaction,
                 json.dumps(detail, ensure_ascii=False), json.dumps(codes, ensure_ascii=False), now_iso()),
            )
        verified += 1
    return {"verified": verified, "reacted": reacted, "targets": len(targets)}
