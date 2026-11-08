"""End-to-end AI pipeline: collect → analyze → opportunities → weekly simulation.

This is the user-facing flow; each stage is explicit and failures are reported
per stage instead of silently producing numbers.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone, timedelta

from ..ai import make_client
from ..ai.service import analyze_pending
from ..analysis.recommendations import list_recommendations, run_recommendations
from ..content.service import sync_announcements, sync_news
from ..content.global_news import sync_global_news
from ..content.verification import verify_content
from ..trading_plan.service import (
    build_trade_plans,
    latest_weekly_sim,
    list_trade_plans,
    market_regime,
    start_weekly_sim,
)

TZ = timezone(timedelta(hours=8))


def _counts(conn: sqlite3.Connection) -> dict:
    news = conn.execute("SELECT COUNT(*) AS n, MAX(fetched_at) AS last FROM news_items").fetchone()
    glob = conn.execute("SELECT COUNT(*) AS n, MAX(fetched_at) AS last FROM global_news").fetchone()
    verified = conn.execute("SELECT COUNT(*) AS n FROM news_verification").fetchone()["n"]
    reacted = conn.execute("SELECT COUNT(*) AS n FROM news_verification WHERE price_reaction IN ('REACTED_UP','REACTED_DOWN','MOVED_BEFORE')").fetchone()["n"]
    ann = conn.execute("SELECT COUNT(*) AS n, MAX(fetched_at) AS last FROM announcements").fetchone()
    analyzed = conn.execute("SELECT COUNT(*) AS n FROM ai_analysis").fetchone()["n"]
    pending = conn.execute(
        """
        SELECT
          (SELECT COUNT(*) FROM news_items n LEFT JOIN ai_analysis a
             ON a.target_type='news' AND a.target_id=n.id WHERE a.id IS NULL)
          +
          (SELECT COUNT(*) FROM announcements x LEFT JOIN ai_analysis a
             ON a.target_type='announcement' AND a.target_id=x.id WHERE a.id IS NULL)
          AS n
        """
    ).fetchone()["n"]
    failed = conn.execute("SELECT COUNT(*) AS n FROM ai_tasks WHERE status='FAILED'").fetchone()["n"]
    return {
        "news_count": news["n"], "last_news_at": news["last"],
        "global_news_count": glob["n"], "last_global_at": glob["last"],
        "verified_count": verified, "price_reacted_count": reacted,
        "announcement_count": ann["n"], "last_announcement_at": ann["last"],
        "analyzed_count": analyzed, "pending_analysis": pending, "failed_tasks": failed,
    }


def status(conn: sqlite3.Connection) -> dict:
    plans = list_trade_plans(conn)
    return {
        **_counts(conn),
        "market_regime": market_regime(conn),
        "opportunities": plans,
        "recos": list_recommendations(conn),
        "weekly": latest_weekly_sim(conn),
    }


def run_pipeline(
    conn: sqlite3.Connection,
    collect: bool = True,
    days: int = 3,
    max_pages: int = 2,
    analyze_limit: int = 6,
    provider: str = "deepseek",
    model: str = "deepseek-chat",
    client=None,
) -> dict:
    stages: list[dict] = []
    collected = None
    if collect:
        try:
            ann = sync_announcements(conn, days=max(1, min(days, 30)), max_pages=max(1, min(max_pages, 20)))
            news = sync_news(conn)
            glob = sync_global_news(conn)
            collected = {"announcements": ann, "news": news, "global": glob}
            stages.append({"key": "collect", "status": "ok", "detail": collected})
        except Exception as exc:  # noqa: BLE001
            stages.append({"key": "collect", "status": "error", "detail": str(exc)})

    try:
        ver = verify_content(conn)
        stages.append({"key": "verify", "status": "ok", "detail": ver})
    except Exception as exc:  # noqa: BLE001
        stages.append({"key": "verify", "status": "error", "detail": str(exc)})

    if client is None:
        client = make_client(provider, model)
    if not client.available():
        stages.append({"key": "analyze", "status": "error",
                       "detail": f"{provider}:{model} 不可用（检查 Key/本地模型）"})
    else:
        try:
            analyzed = analyze_pending(conn, client, limit=max(1, min(analyze_limit, 20)),
                                       model_id=f"{provider}:{model}")
            stages.append({"key": "analyze", "status": "ok", "detail": analyzed})
        except Exception as exc:  # noqa: BLE001
            stages.append({"key": "analyze", "status": "error", "detail": str(exc)})

    try:
        run_recommendations(conn, model_id=f"{provider}:{model}")
        stages.append({"key": "opportunities", "status": "ok",
                       "detail": {"note": "已按 AI 分析生成买入候选/持仓建议"}})
    except Exception as exc:  # noqa: BLE001
        stages.append({"key": "opportunities", "status": "error", "detail": str(exc)})

    try:
        plans = build_trade_plans(conn, model_id=f"{provider}:{model}")
        stages.append({"key": "plans", "status": "ok", "detail": plans})
    except Exception as exc:  # noqa: BLE001
        stages.append({"key": "plans", "status": "error", "detail": str(exc)})

    try:
        existing = latest_weekly_sim(conn)
        if existing and existing["sim"]["status"] in ("PENDING", "ACTIVE"):
            stages.append({"key": "simulate", "status": "ok",
                           "detail": {"note": "已有进行中的一周模拟，沿用", "start_date": existing["sim"]["start_date"]}})
        else:
            sim = start_weekly_sim(conn)
            stages.append({"key": "simulate", "status": "ok", "detail": sim})
    except Exception as exc:  # noqa: BLE001
        stages.append({"key": "simulate", "status": "error", "detail": str(exc)})

    return {"stages": stages, **status(conn)}

