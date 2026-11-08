"""AI analysis service (P3).

Pipeline: pending news/announcement -> LLM JSON -> schema + evidence validation
-> ai_analysis -> alerts (L2-L4). Invalid outputs are recorded as failed tasks
and are never turned into analysis or alerts.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone, timedelta

from .clients import AiUnavailable
from .models import AnalysisResult

TZ = timezone(timedelta(hours=8))

ALERT_RULES = [
    ("L1", "关注", "Watch", "信息值得关注，暂不构成交易动作"),
    ("L2", "重要", "Important", "对股价/基本面有实质影响"),
    ("L3", "重大", "Major", "重大事件，需重点跟踪"),
    ("L4", "紧急", "Urgent", "紧急风险或重大机会，立即处理"),
]
ALERT_LEVELS = {"L2", "L3", "L4"}


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def ensure_alert_rules(conn: sqlite3.Connection) -> None:
    with conn:
        conn.executemany(
            """
            INSERT INTO alert_rules(level, name_zh, name_en, condition_json, enabled, updated_at)
            VALUES (?, ?, ?, ?, 1, ?)
            ON CONFLICT(level) DO UPDATE SET
                name_zh=excluded.name_zh, name_en=excluded.name_en, updated_at=excluded.updated_at
            """,
            [(lvl, zh, en, json.dumps({"note": note}, ensure_ascii=False), now_iso()) for lvl, zh, en, note in ALERT_RULES],
        )


def _pending_targets(conn: sqlite3.Connection, limit: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT 'news' AS target_type, n.id, n.title, n.summary, n.url, n.published_at
        FROM news_items n
        LEFT JOIN ai_analysis a ON a.target_type='news' AND a.target_id=n.id
        WHERE a.id IS NULL
        ORDER BY COALESCE(n.published_at, n.fetched_at) DESC, n.id ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    targets = [dict(r) for r in rows]
    if len(targets) < limit:
        rows2 = conn.execute(
            """
            SELECT 'announcement' AS target_type, x.id, x.title, NULL AS summary, x.url, x.published_at
            FROM announcements x
            LEFT JOIN ai_analysis a ON a.target_type='announcement' AND a.target_id=x.id
            WHERE a.id IS NULL
            ORDER BY COALESCE(x.published_at, x.fetched_at) DESC, x.id ASC
            LIMIT ?
            """,
            (limit - len(targets),),
        ).fetchall()
        targets.extend(dict(r) for r in rows2)
    return targets


def build_prompt(target: dict) -> str:
    parts = [
        f"类型: {target['target_type']}",
        f"标题: {target['title']}",
    ]
    if target.get("summary"):
        parts.append(f"摘要: {target['summary']}")
    parts.append(f"来源链接: {target.get('url') or ''}")
    parts.append(f"发布时间: {target.get('published_at') or ''}")
    parts.append("请严格按系统提示输出JSON；evidence.quote 必须逐字来自以上文本。")
    return "\n".join(parts)


def _normalize(text: str) -> str:
    return "".join(text.split())


def validate_evidence(result: AnalysisResult, target: dict) -> None:
    source_text = _normalize(f"{target['title']} {target.get('summary') or ''}")
    for ev in result.evidence:
        quote = _normalize(ev.quote)
        if not quote:
            raise ValueError("evidence quote empty")
        if quote not in source_text:
            raise ValueError("EVIDENCE_NOT_IN_SOURCE")


def _task_upsert(conn: sqlite3.Connection, target: dict, status: str, error: str | None, model_id: str | None) -> None:
    ts = now_iso()
    with conn:
        conn.execute(
            """
            INSERT INTO ai_tasks(task_type, target_type, target_id, status, attempts, error, model_id, created_at, updated_at)
            VALUES ('analysis', ?, ?, ?, 1, ?, ?, ?, ?)
            ON CONFLICT(task_type, target_type, target_id) DO UPDATE SET
                status=excluded.status, attempts=ai_tasks.attempts+1,
                error=excluded.error, model_id=excluded.model_id, updated_at=excluded.updated_at
            """,
            (target["target_type"], target["id"], status, error, model_id, ts, ts),
        )


def analyze_pending(conn: sqlite3.Connection, client, limit: int = 10, model_id: str | None = None) -> dict:
    ensure_alert_rules(conn)
    targets = _pending_targets(conn, limit)
    analyzed = 0
    alerts = 0
    failures: list[str] = []
    for target in targets:
        prompt = build_prompt(target)
        try:
            raw = client.analyze(prompt)
            result = AnalysisResult.model_validate(raw)
            validate_evidence(result, target)
        except Exception as exc:  # noqa: BLE001 - schema/evidence/model errors are task failures
            _task_upsert(conn, target, "FAILED", f"{type(exc).__name__}: {exc}", model_id)
            failures.append(f"{target['target_type']}:{target['id']}: {exc}")
            continue

        ts = now_iso()
        with conn:
            conn.execute(
                """
                INSERT INTO ai_analysis(target_type, target_id, event_type, sentiment, materiality,
                    summary, stocks_json, evidence_json, model_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(target_type, target_id) DO UPDATE SET
                    event_type=excluded.event_type, sentiment=excluded.sentiment,
                    materiality=excluded.materiality, summary=excluded.summary,
                    stocks_json=excluded.stocks_json, evidence_json=excluded.evidence_json,
                    model_id=excluded.model_id
                """,
                (
                    target["target_type"], target["id"], result.event_type, result.sentiment,
                    result.materiality, result.summary,
                    json.dumps(result.stocks, ensure_ascii=False),
                    json.dumps([e.model_dump() for e in result.evidence], ensure_ascii=False),
                    model_id, ts,
                ),
            )
            if result.materiality in ALERT_LEVELS:
                conn.execute(
                    """
                    INSERT INTO alerts(level, title, summary, security_codes_json, evidence_json,
                        source_type, source_id, status, triggered_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?)
                    """,
                    (
                        result.materiality,
                        target["title"][:200],
                        result.summary,
                        json.dumps(result.stocks, ensure_ascii=False),
                        json.dumps([e.model_dump() for e in result.evidence], ensure_ascii=False),
                        target["target_type"],
                        target["id"],
                        ts,
                        ts,
                    ),
                )
                alerts += 1
        _task_upsert(conn, target, "DONE", None, model_id)
        analyzed += 1
    return {"pending": len(targets), "analyzed": analyzed, "alerts": alerts, "failures": failures}


def ai_status(conn: sqlite3.Connection, client) -> dict:
    counts = {}
    for table in ("ai_analysis", "alerts", "ai_tasks"):
        counts[table] = int(conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"])
    try:
        available = bool(client.available()) if hasattr(client, "available") else False
    except Exception:  # noqa: BLE001
        available = False
    return {"available": available, "counts": counts}


def list_analysis(conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM ai_analysis ORDER BY created_at DESC LIMIT ?", (max(1, min(limit, 500)),)
    ).fetchall()
    out = []
    for r in rows:
        item = dict(r)
        item["stocks"] = json.loads(item.pop("stocks_json") or "[]")
        item["evidence"] = json.loads(item.pop("evidence_json") or "[]")
        out.append(item)
    return out


def list_alerts(conn: sqlite3.Connection, level: str | None = None, limit: int = 50) -> list[dict]:
    sql = "SELECT * FROM alerts"
    args: list = []
    if level:
        sql += " WHERE level = ?"
        args.append(level)
    sql += " ORDER BY triggered_at DESC LIMIT ?"
    args.append(max(1, min(limit, 500)))
    out = []
    for r in conn.execute(sql, args).fetchall():
        item = dict(r)
        item["security_codes"] = json.loads(item.pop("security_codes_json") or "[]")
        item["evidence"] = json.loads(item.pop("evidence_json") or "[]")
        out.append(item)
    return out


def acknowledge_alert(conn: sqlite3.Connection, alert_id: int) -> bool:
    with conn:
        cur = conn.execute(
            "UPDATE alerts SET status='ACK', updated_at=? WHERE id=? AND status='OPEN'", (now_iso(), alert_id)
        )
    return cur.rowcount > 0


def analyze_selected(conn: sqlite3.Connection, client, selected: list[dict], model_id: str | None = None) -> dict:
    """Analyze explicitly selected targets (scripts/tests). Same validation as batch."""
    ensure_alert_rules(conn)
    analyzed = 0
    alerts = 0
    failures: list[str] = []
    for target in selected:
        prompt = build_prompt(target)
        try:
            raw = client.analyze(prompt)
            result = AnalysisResult.model_validate(raw)
            validate_evidence(result, target)
        except Exception as exc:  # noqa: BLE001
            _task_upsert(conn, target, "FAILED", f"{type(exc).__name__}: {exc}", model_id)
            failures.append(f"{target['target_type']}:{target['id']}: {exc}")
            continue
        ts = now_iso()
        with conn:
            conn.execute(
                """
                INSERT INTO ai_analysis(target_type, target_id, event_type, sentiment, materiality,
                    summary, stocks_json, evidence_json, model_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(target_type, target_id) DO UPDATE SET
                    event_type=excluded.event_type, sentiment=excluded.sentiment,
                    materiality=excluded.materiality, summary=excluded.summary,
                    stocks_json=excluded.stocks_json, evidence_json=excluded.evidence_json,
                    model_id=excluded.model_id
                """,
                (target["target_type"], target["id"], result.event_type, result.sentiment,
                 result.materiality, result.summary, json.dumps(result.stocks, ensure_ascii=False),
                 json.dumps([e.model_dump() for e in result.evidence], ensure_ascii=False), model_id, ts),
            )
            if result.materiality in ALERT_LEVELS:
                conn.execute(
                    "INSERT INTO alerts(level,title,summary,security_codes_json,evidence_json,source_type,source_id,status,triggered_at,updated_at) "
                    "VALUES (?,?,?,?,?,?,?, 'OPEN', ?, ?)",
                    (result.materiality, target["title"][:200], result.summary,
                     json.dumps(result.stocks, ensure_ascii=False),
                     json.dumps([e.model_dump() for e in result.evidence], ensure_ascii=False),
                     target["target_type"], target["id"], ts, ts),
                )
                alerts += 1
        _task_upsert(conn, target, "DONE", None, model_id)
        analyzed += 1
    return {"pending": len(selected), "analyzed": analyzed, "alerts": alerts, "failures": failures}
