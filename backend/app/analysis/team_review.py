"""AI team review: technical + news + capital + risk roles in one evidence-bound call.

Extracted concept from the reference project (technical/fundamental/capital/risk/
sentiment agents + team discussion + final decision), reimplemented for this
codebase: single structured call, strict evidence validation, no fabricated
financial statements (data gaps are stated explicitly).
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone, timedelta

from .technicals import compute_indicators, load_bars

TZ = timezone(timedelta(hours=8))

TEAM_SCHEMA = {
    "type": "object",
    "properties": {
        "rating": {"enum": ["BUY", "HOLD", "SELL"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "summary": {"type": "string"},
        "technical_view": {"type": "string"},
        "news_view": {"type": "string"},
        "risk_view": {"type": "string"},
        "entry_price": {"type": ["number", "null"]},
        "target_price": {"type": ["number", "null"]},
        "stop_loss": {"type": ["number", "null"]},
        "reasons": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
        "evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"quote": {"type": "string"}, "source": {"type": "string"}},
                "required": ["quote", "source"],
            },
        },
    },
    "required": ["rating", "confidence", "summary", "technical_view", "news_view", "risk_view",
                 "entry_price", "target_price", "stop_loss", "reasons", "risks", "evidence"],
}

SYSTEM_PROMPT = """你是A股研究团队（技术分析师、新闻/情绪分析师、资金面分析师、风险管理师）。
只依据输入数据输出严格JSON，不得编造不存在的财务数据、订单、价格或新闻。
- rating: BUY / HOLD / SELL
- confidence: 0~1
- entry_price/target_price/stop_loss: 数字或 null；SELL 时 entry 为参考卖出价
- evidence.quote 必须逐字来自输入中的“新闻/公告原文”，没有原文则输出空数组
- 技术面只能基于给定的指标；新闻面只能基于给定的新闻摘要；财务数据缺失时必须写“未提供财务数据”，不能猜。
- summary 不超过200字。"""


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def _norm(text: str) -> str:
    return "".join((text or "").split())


def build_context(conn: sqlite3.Connection, code: str) -> dict:
    sec = conn.execute("SELECT code, name_zh, exchange, board FROM securities WHERE code=?", (code,)).fetchone()
    quote = conn.execute(
        "SELECT last, change_pct, quote_time, source_id, is_realtime, license_status FROM stock_quotes WHERE code=?",
        (code,),
    ).fetchone()
    indicators = compute_indicators(load_bars(conn, code, 120))
    analyses = conn.execute(
        """
        SELECT a.id, a.sentiment, a.materiality, a.summary, a.created_at, a.model_id,
               l.target_type, l.target_id
        FROM ai_analysis a
        JOIN news_stock_links l ON l.target_type=a.target_type AND l.target_id=a.target_id
        WHERE l.code=?
        ORDER BY a.created_at DESC LIMIT 8
        """,
        (code,),
    ).fetchall()
    items = []
    corpus = []
    for row in analyses:
        if row["target_type"] == "news":
            t = conn.execute("SELECT title, summary, url, published_at FROM news_items WHERE id=?", (row["target_id"],)).fetchone()
        elif row["target_type"] == "announcement":
            t = conn.execute("SELECT title, NULL AS summary, url, published_at FROM announcements WHERE id=?", (row["target_id"],)).fetchone()
        else:
            t = conn.execute("SELECT title, summary, url, published_at FROM global_news WHERE id=?", (row["target_id"],)).fetchone()
        if not t:
            continue
        text = f"{t['title'] or ''} {t['summary'] or ''}".strip()
        corpus.append(_norm(text))
        items.append({
            "sentiment": row["sentiment"], "materiality": row["materiality"], "summary": row["summary"],
            "title": t["title"], "source_text": text, "url": t["url"], "published_at": t["published_at"],
        })
    return {
        "code": code,
        "name": sec["name_zh"] if sec else None,
        "market": f"{sec['exchange']}/{sec['board']}" if sec else None,
        "quote": dict(quote) if quote else None,
        "indicators": indicators,
        "news": items,
        "corpus": corpus,
        "financial": {"status": "NOT_PROVIDED", "note": "财报结构化数据尚未接入；禁止编造财务数字"},
    }


def build_prompt(ctx: dict) -> str:
    return (
        f"股票：{ctx['name'] or ''} ({ctx['code']})，市场 {ctx['market']}\n"
        f"最新行情（未授权快照，非实时）：{json.dumps(ctx['quote'], ensure_ascii=False)}\n"
        f"技术指标（本地日线计算）：{json.dumps(ctx['indicators'], ensure_ascii=False)}\n"
        f"财务数据：{json.dumps(ctx['financial'], ensure_ascii=False)}\n"
        f"近期AI分析/新闻/公告：{json.dumps(ctx['news'], ensure_ascii=False)}\n"
        "请输出团队研判JSON。"
    )


def _validate(result: dict, ctx: dict) -> dict:
    if result.get("rating") not in ("BUY", "HOLD", "SELL"):
        raise ValueError("invalid rating")
    conf = result.get("confidence")
    if not isinstance(conf, (int, float)) or not 0 <= float(conf) <= 1:
        raise ValueError("invalid confidence")
    for key in ("entry_price", "target_price", "stop_loss"):
        value = result.get(key)
        if value is not None and (not isinstance(value, (int, float)) or value <= 0):
            raise ValueError(f"invalid {key}")
    if result.get("rating") == "BUY" and all(result.get(k) is not None for k in ("entry_price", "stop_loss", "target_price")):
        if not (result["stop_loss"] < result["entry_price"] < result["target_price"]):
            raise ValueError("BUY prices must satisfy stop_loss < entry < target")
    corpus = ctx["corpus"]
    raw_evidence = result.get("evidence")
    if isinstance(raw_evidence, str):
        result["evidence"] = [{"quote": raw_evidence, "source": ""}]
    elif isinstance(raw_evidence, list):
        normalized = []
        for item in raw_evidence:
            if isinstance(item, str):
                normalized.append({"quote": item, "source": ""})
            elif isinstance(item, dict):
                normalized.append(item)
            else:
                raise ValueError("invalid evidence item")
        result["evidence"] = normalized
    else:
        result["evidence"] = []
    for ev in result.get("evidence") or []:
        quote = _norm(ev.get("quote", ""))
        if not quote:
            raise ValueError("empty evidence quote")
        if corpus and not any(quote in text for text in corpus):
            raise ValueError("EVIDENCE_NOT_IN_SOURCE")
    if result.get("evidence") and not corpus:
        raise ValueError("evidence without source text")
    return result


def run_team_review(conn: sqlite3.Connection, code: str, client, model_id: str | None = None) -> dict:
    ctx = build_context(conn, code)
    if not ctx["indicators"].get("ok"):
        raise ValueError(f"历史日线不足：{ctx['indicators'].get('reason')}")
    raw = client.complete_json(SYSTEM_PROMPT, build_prompt(ctx), TEAM_SCHEMA)
    result = _validate(raw, ctx)
    as_of = ctx["indicators"].get("as_of") or datetime.now(TZ).date().isoformat()
    with conn:
        conn.execute(
            """
            INSERT INTO ai_team_reviews(code, as_of, rating, confidence, summary, technical_view,
                news_view, risk_view, decision_json, evidence_json, indicators_json, model_id, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(code, as_of, model_id) DO UPDATE SET
                rating=excluded.rating, confidence=excluded.confidence, summary=excluded.summary,
                technical_view=excluded.technical_view, news_view=excluded.news_view,
                risk_view=excluded.risk_view, decision_json=excluded.decision_json,
                evidence_json=excluded.evidence_json, indicators_json=excluded.indicators_json
            """,
            (code, as_of, result["rating"], result["confidence"], result.get("summary"),
             result.get("technical_view"), result.get("news_view"), result.get("risk_view"),
             json.dumps(result, ensure_ascii=False), json.dumps(result.get("evidence") or [], ensure_ascii=False),
             json.dumps(ctx["indicators"], ensure_ascii=False), model_id, now_iso()),
        )
    return {"code": code, "as_of": as_of, "review": result, "indicators": ctx["indicators"],
            "news_count": len(ctx["news"]), "model_id": model_id}


def list_team_reviews(conn: sqlite3.Connection, code: str | None = None, limit: int = 20) -> list[dict]:
    sql = "SELECT * FROM ai_team_reviews"
    args: list = []
    if code:
        sql += " WHERE code=?"
        args.append(code)
    sql += " ORDER BY created_at DESC LIMIT ?"
    args.append(max(1, min(limit, 100)))
    out = []
    for row in conn.execute(sql, args).fetchall():
        item = dict(row)
        for key in ("decision_json", "evidence_json", "indicators_json"):
            item[key[:-5]] = json.loads(item.pop(key) or "null")
        out.append(item)
    return out

