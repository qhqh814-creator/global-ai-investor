"""Evidence-linked AI recommendations (P3/P4 round 2).

Buy candidates come from positive AI analyses (L2-L4) linked to real stocks;
sell/reduce advice for current paper positions comes from negative analyses
plus explicit risk rules. Every recommendation carries evidence quotes/URLs and
a data-provenance snapshot. Missing evidence yields NO recommendation, never a
fabricated one.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone, timedelta

from .stock_links import links_for_analysis, sync_stock_links

TZ = timezone(timedelta(hours=8))
LOOKBACK_DAYS = 14
WEIGHT = {"L2": 1.0, "L3": 2.0, "L4": 3.0}
NEGATIVE_ACTIONS = {"L4": "SELL", "L3": "SELL", "L2": "REDUCE"}


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def _target_title(conn: sqlite3.Connection, target_type: str, target_id: int) -> dict:
    if target_type == "news":
        row = conn.execute("SELECT title, url, published_at, source_id FROM news_items WHERE id=?", (target_id,)).fetchone()
    else:
        row = conn.execute("SELECT title, url, published_at, source_id FROM announcements WHERE id=?", (target_id,)).fetchone()
    return dict(row) if row else {}


def _analyses_with_links(conn: sqlite3.Connection, sentiment: str) -> list[dict]:
    since = (datetime.now(TZ) - timedelta(days=LOOKBACK_DAYS)).isoformat(timespec="seconds")
    rows = conn.execute(
        """
        SELECT a.id, a.target_type, a.target_id, a.event_type, a.sentiment, a.materiality, a.summary,
               a.evidence_json, a.model_id, a.created_at
        FROM ai_analysis a
        WHERE a.sentiment = ? AND a.materiality IN ('L2','L3','L4') AND a.created_at >= ?
        ORDER BY a.created_at DESC
        """,
        (sentiment, since),
    ).fetchall()
    return [dict(r) for r in rows]


def _analysis_evidence(conn: sqlite3.Connection, analysis: dict) -> dict:
    target = _target_title(conn, analysis["target_type"], analysis["target_id"])
    return {
        "analysis_id": analysis["id"],
        "target_type": analysis["target_type"],
        "target_id": analysis["target_id"],
        "title": target.get("title"),
        "url": target.get("url"),
        "published_at": target.get("published_at"),
        "source_id": target.get("source_id"),
        "event_type": analysis["event_type"],
        "sentiment": analysis["sentiment"],
        "materiality": analysis["materiality"],
        "summary": analysis["summary"],
        "quotes": json.loads(analysis["evidence_json"] or "[]"),
        "model_id": analysis["model_id"],
    }


def _quote_snapshot(conn: sqlite3.Connection, code: str) -> dict | None:
    row = conn.execute(
        "SELECT last, change_pct, prev_close, quote_time, source_id, is_realtime, license_status, fetched_at "
        "FROM stock_quotes WHERE code = ?",
        (code,),
    ).fetchone()
    return dict(row) if row else None


def _security_name(conn: sqlite3.Connection, code: str) -> str | None:
    row = conn.execute("SELECT name_zh FROM securities WHERE code = ?", (code,)).fetchone()
    return row["name_zh"] if row else None


def _insert_recommendation(conn: sqlite3.Connection, run_id: int, reco: dict, model_id: str | None) -> None:
    with conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO ai_recommendations(
                run_id, reco_type, trade_date, code, name, action, confidence, score, horizon_days,
                reason_summary, reasons_json, evidence_json, source_analysis_json, quote_json, position_json,
                status, model_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?)
            """,
            (
                run_id, reco["reco_type"], reco["trade_date"], reco["code"], reco["name"], reco["action"],
                reco["confidence"], reco["score"], reco["horizon_days"], reco["reason_summary"],
                json.dumps(reco["reasons"], ensure_ascii=False),
                json.dumps(reco["evidence"], ensure_ascii=False),
                json.dumps(reco["source_analyses"], ensure_ascii=False),
                json.dumps(reco["quote"], ensure_ascii=False),
                json.dumps(reco.get("position"), ensure_ascii=False),
                model_id, now_iso(),
            ),
        )


def build_buy_candidates(conn: sqlite3.Connection) -> list[dict]:
    rows = _analyses_with_links(conn, "positive")
    by_code: dict[str, dict] = {}
    for analysis in rows:
        for link in links_for_analysis(conn, analysis["target_type"], analysis["target_id"]):
            code = link["code"]
            item = by_code.setdefault(code, {"analyses": [], "score": 0.0, "materialities": []})
            item["analyses"].append(analysis)
            item["score"] += WEIGHT.get(analysis["materiality"], 0.5) * link["confidence"]
            item["materialities"].append(analysis["materiality"])
    out = []
    for code, item in by_code.items():
        analyses = item["analyses"]
        evidence = [_analysis_evidence(conn, a) for a in analyses]
        quote = _quote_snapshot(conn, code)
        name = _security_name(conn, code)
        top_materiality = max(item["materialities"], key=lambda m: WEIGHT.get(m, 0))
        confidence = min(0.9, 0.4 + 0.15 * len(analyses) + 0.1 * WEIGHT.get(top_materiality, 0))
        reasons = []
        for a in analyses[:5]:
            reasons.append({
                "type": "news_event",
                "text": f"[{a['materiality']}] {a['event_type']}：{a['summary']}",
                "analysis_id": a["id"],
            })
        out.append({
            "reco_type": "BUY",
            "trade_date": (quote["quote_time"][:10] if quote and quote.get("quote_time") else datetime.now(TZ).date().isoformat()),
            "code": code,
            "name": name,
            "action": "BUY_CANDIDATE",
            "confidence": round(confidence, 2),
            "score": round(item["score"], 3),
            "horizon_days": 10,
            "reason_summary": f"近{LOOKBACK_DAYS}天有{len(analyses)}条正向AI分析（最高{top_materiality}），证据见下。",
            "reasons": reasons,
            "evidence": evidence,
            "source_analyses": [a["id"] for a in analyses],
            "quote": quote,
        })
    out.sort(key=lambda x: (x["score"], x["confidence"]), reverse=True)
    return out


def build_position_advice(conn: sqlite3.Connection) -> list[dict]:
    positions = conn.execute(
        """
        SELECT p.code, p.qty, p.sellable_qty, p.avg_cost, p.buy_date, s.name_zh
        FROM sim_positions p LEFT JOIN securities s ON s.code = p.code
        """
    ).fetchall()
    negative_rows = _analyses_with_links(conn, "negative")
    neg_by_code: dict[str, list[dict]] = {}
    for analysis in negative_rows:
        for link in links_for_analysis(conn, analysis["target_type"], analysis["target_id"]):
            neg_by_code.setdefault(link["code"], []).append(analysis)

    out = []
    for pos in positions:
        code = pos["code"]
        quote = _quote_snapshot(conn, code)
        negatives = neg_by_code.get(code, [])
        reasons: list[dict] = []
        evidence = [_analysis_evidence(conn, a) for a in negatives]
        action = "HOLD"
        confidence = 0.3
        if negatives:
            top = max(negatives, key=lambda a: WEIGHT.get(a["materiality"], 0))
            action = NEGATIVE_ACTIONS.get(top["materiality"], "REDUCE")
            confidence = min(0.9, 0.45 + 0.15 * len(negatives))
            for a in negatives[:5]:
                reasons.append({
                    "type": "negative_news",
                    "text": f"[{a['materiality']}] {a['event_type']}：{a['summary']}",
                    "analysis_id": a["id"],
                })
        else:
            reasons.append({"type": "no_negative_evidence", "text": "近14天未发现针对该公司的负向AI分析；不构成卖出依据。"})

        if quote and quote.get("last") and pos["avg_cost"]:
            pnl_pct = (quote["last"] - pos["avg_cost"]) / pos["avg_cost"]
            reasons.append({
                "type": "position_pnl",
                "text": f"持仓成本 {pos['avg_cost']:.4f}，最新价 {quote['last']:.2f}，浮动盈亏 {pnl_pct*100:.2f}%（第三方快照，非实时，数据时间 {quote.get('quote_time')}）。",
            })
            if pnl_pct <= -0.08 and action == "HOLD":
                action = "REDUCE"
                confidence = max(confidence, 0.5)
                reasons.append({"type": "stop_loss_rule", "text": "浮亏超过8%触发风险减仓规则（规则非AI判断）。"})
        else:
            reasons.append({"type": "quote_unavailable", "text": "最新行情不可用，无法计算持仓盈亏；不下结论。"})
            if action == "SELL":
                action = "SELL"
            else:
                confidence = 0.2

        out.append({
            "reco_type": "HOLDING",
            "trade_date": (quote["quote_time"][:10] if quote and quote.get("quote_time") else datetime.now(TZ).date().isoformat()),
            "code": code,
            "name": pos["name_zh"],
            "action": action,
            "confidence": round(confidence, 2),
            "score": round(WEIGHT.get(max([a["materiality"] for a in negatives], key=lambda m: WEIGHT.get(m, 0)), 0) if negatives else 0, 3),
            "horizon_days": 10,
            "reason_summary": "基于负向AI分析与持仓风险规则；证据不足时明确持有/观察。" if negatives else "未发现卖出证据，按持仓风险规则给出建议。",
            "reasons": reasons,
            "evidence": evidence,
            "source_analyses": [a["id"] for a in negatives],
            "quote": quote,
            "position": {
                "qty": pos["qty"], "sellable_qty": pos["sellable_qty"],
                "avg_cost": pos["avg_cost"], "buy_date": pos["buy_date"],
            },
        })
    return out


def run_recommendations(conn: sqlite3.Connection, model_id: str | None = None) -> dict:
    links = sync_stock_links(conn)
    params = {"lookback_days": LOOKBACK_DAYS, "buy_source": "positive L2-L4 analyses", "sell_source": "negative L2-L4 analyses + risk rules"}
    with conn:
        # keep history but only the newest run is ACTIVE
        conn.execute("UPDATE ai_recommendations SET status='SUPERSEDED' WHERE status='ACTIVE'")
        cur = conn.execute(
            "INSERT INTO recommendation_runs(model_id, params_json, stats_json, created_at) VALUES (?, ?, NULL, ?)",
            (model_id, json.dumps(params, ensure_ascii=False), now_iso()),
        )
        run_id = int(cur.lastrowid)
    buys = build_buy_candidates(conn)
    holds = build_position_advice(conn)
    for reco in buys + holds:
        _insert_recommendation(conn, run_id, reco, model_id)
    stats = {"buy_candidates": len(buys), "holding_advice": len(holds), "links": links["inserted"]}
    with conn:
        conn.execute("UPDATE recommendation_runs SET stats_json=? WHERE id=?", (json.dumps(stats, ensure_ascii=False), run_id))
    return {"run_id": run_id, "stats": stats}


def list_recommendations(conn: sqlite3.Connection, reco_type: str | None = None, limit: int = 100) -> list[dict]:
    sql = "SELECT * FROM ai_recommendations WHERE status='ACTIVE'"
    args: list = []
    if reco_type:
        sql += " AND reco_type = ?"
        args.append(reco_type)
    sql += " ORDER BY trade_date DESC, score DESC, confidence DESC LIMIT ?"
    args.append(max(1, min(limit, 500)))
    out = []
    for row in conn.execute(sql, args).fetchall():
        item = dict(row)
        for key in ("reasons_json", "evidence_json", "source_analysis_json", "quote_json", "position_json"):
            raw = item.pop(key)
            if key == "quote_json":
                item["quote"] = json.loads(raw) if raw else None
            elif key == "position_json":
                item["position"] = json.loads(raw) if raw else None
            else:
                item[key[:-5]] = json.loads(raw) if raw else []
        out.append(item)
    return out


def get_recommendation(conn: sqlite3.Connection, reco_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM ai_recommendations WHERE id=?", (reco_id,)).fetchone()
    if not row:
        return None
    item = dict(row)
    item["reasons"] = json.loads(item.pop("reasons_json") or "[]")
    item["evidence"] = json.loads(item.pop("evidence_json") or "[]")
    item["source_analyses"] = json.loads(item.pop("source_analysis_json") or "[]")
    item["quote"] = json.loads(item.pop("quote_json") or "null")
    raw_position = item.pop("position_json", None)
    item["position"] = json.loads(raw_position) if raw_position else None
    return item



