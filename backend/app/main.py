"""Global AI Investor V1.0 backend (FastAPI sidecar).

P1: rule library, trading calendar, fee/order validation endpoints.
Data collection and AI modules land in P2/P3.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel
from fastapi.responses import JSONResponse

from .datasources.securities_lists import fetch_bse, fetch_sse, fetch_szse
from .db.migrate import migrate
from .analysis import get_recommendation, list_recommendations, run_recommendations, sync_stock_links
from .ai.secrets import set_secret
from .ai import (
    AiUnavailable,
    acknowledge_alert,
    ai_status,
    analyze_pending,
    ensure_alert_rules,
    list_alerts,
    list_analysis,
    make_client,
)
from .backtest import get_backtest, run_backtest
from .content import list_announcements, list_global_news, list_news, sync_announcements, sync_news
from .klines import sync_daily
from .pipeline import run_pipeline, status as pipeline_status
from .paper import get_account, list_orders as paper_orders, list_trades as paper_trades, place_order, reset_account
from .predictions import accuracy, create_prediction, list_predictions, settle_predictions
from .quotes import get_dashboard, sync_quotes
from .screening import latest_run, run_screening
from .signals import ensure_default_rules, list_signals, run_signals
from .watchlist import add_item, ensure_default_watchlist, list_items, list_watchlists, remove_item
from .workers import run_job_now, start_scheduler, stop_scheduler
from .rules import get_library
from .rules.store import list_versions as db_rule_versions, stats as db_rule_stats, sync_library
from .securities import list_securities, stats as securities_stats, upsert_securities
from .securities.fallback import ensure_data_source, populate_from_quotes
from .trading_calendar import TradingCalendar
from .trading_plan import build_trade_plans, evaluate_weekly, latest_weekly_sim, list_trade_plans, market_regime, start_weekly_sim

ROOT = Path(os.environ.get("GAI_ROOT", Path(__file__).resolve().parents[2]))
DATA_DIR = ROOT / "data"
DB_DIR = DATA_DIR / "db"
DB_PATH = DB_DIR / "gai.db"
TOKEN = os.environ.get("GAI_TOKEN", "")
PORT = int(os.environ.get("GAI_PORT", "0"))

app = FastAPI(title="Global AI Investor Backend", version="0.1.0")


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def get_db() -> sqlite3.Connection:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def bootstrap() -> None:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    with get_db() as conn:
        migrate(conn)
        sync_library(conn)
        ensure_alert_rules(conn)
        ensure_default_watchlist(conn)
        ensure_default_rules(conn)
        conn.execute(
            "INSERT OR REPLACE INTO app_settings(key, value_json, updated_at) VALUES (?, ?, ?)",
            ("app.last_start", json.dumps({"started_at": now_iso()}), now_iso()),
        )
        conn.execute(
            "INSERT OR REPLACE INTO data_sources(source_id, name, kind, base_url, license_status, commercial_ok, latency_class, enabled, config_json, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
            (
                "szse_calendar",
                "深圳证券交易所交易日历",
                "calendar",
                "https://www.szse.cn/api/report/exchange/onepersistenthour/monthList",
                "public_page",
                0,
                "eod",
                json.dumps({"note": "官方公开接口，实测可用"}),
                now_iso(),
            ),
        )


async def require_token(request: Request) -> None:
    if not TOKEN:
        return
    if request.headers.get("Authorization", "") != f"Bearer {TOKEN}":
        raise HTTPException(status_code=401, detail="unauthorized")


@app.on_event("startup")
def on_startup() -> None:
    bootstrap()
    start_scheduler(get_db)


@app.on_event("shutdown")
def on_shutdown() -> None:
    stop_scheduler()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "gai-backend", "version": "0.1.0", "port": PORT, "time": now_iso()}


@app.get("/api/status", dependencies=[Depends(require_token)])
def status() -> dict:
    with get_db() as conn:
        migrations = conn.execute("SELECT COUNT(*) AS c FROM schema_migrations").fetchone()["c"]
        cal = conn.execute("SELECT COUNT(*) AS c FROM trading_calendar").fetchone()["c"]
        try:
            versions = len(get_library().versions)
        except Exception as exc:  # pragma: no cover - surfaced to UI
            versions = f"error: {exc}"
    return {
        "ok": True,
        "root": str(ROOT),
        "db": str(DB_PATH),
        "migrations": migrations,
        "trading_calendar_days": cal,
        "rule_versions": versions,
        "time": now_iso(),
    }


@app.get("/api/pipeline/status", dependencies=[Depends(require_token)])
def api_pipeline_status() -> dict:
    with get_db() as conn:
        return pipeline_status(conn)


@app.post("/api/pipeline/run", dependencies=[Depends(require_token)])
def api_pipeline_run(collect: bool = True, days: int = 3, max_pages: int = 2,
                     analyze_limit: int = 6, provider: str = "deepseek", model: str = "deepseek-chat") -> dict:
    with get_db() as conn:
        return run_pipeline(conn, collect=collect, days=days, max_pages=max_pages,
                            analyze_limit=analyze_limit, provider=provider, model=model)

@app.get("/api/dashboard", dependencies=[Depends(require_token)])
def dashboard() -> dict:
    with get_db() as conn:
        return get_dashboard(conn)


@app.post("/api/quotes/sync", dependencies=[Depends(require_token)])
def quotes_sync() -> dict:
    """Fetch index + full-market snapshots from the registered free source.

    The response is a third-party snapshot (not real-time); every card that uses
    it carries provenance. Failures degrade to '数据不可用' rather than fake data.
    """
    with get_db() as conn:
        return sync_quotes(conn)


@app.post("/api/securities/backfill/{exchange}", dependencies=[Depends(require_token)])
def api_securities_backfill(exchange: str) -> dict:
    """Populate missing securities from the latest quote snapshot (third-party source).

    Every row is tagged `eastmoney_quote` / unlicensed; used when an official
    exchange list endpoint is unavailable (currently SZSE WAF blocking).
    """
    exchange = exchange.upper()
    if exchange not in ("SSE", "SZSE", "BSE"):
        raise HTTPException(status_code=422, detail="exchange must be SSE/SZSE/BSE")
    with get_db() as conn:
        ensure_data_source(conn)
        result = populate_from_quotes(conn, exchange)
        return {**result, "stats": securities_stats(conn)}


@app.post("/api/news/sync", dependencies=[Depends(require_token)])
def news_sync() -> dict:
    with get_db() as conn:
        return sync_news(conn)


@app.get("/api/news", dependencies=[Depends(require_token)])
def news_list(limit: int = 50) -> dict:
    with get_db() as conn:
        return {"items": list_news(conn, limit=limit)}


@app.post("/api/announcements/sync", dependencies=[Depends(require_token)])
def announcements_sync(days: int = 7, max_pages: int = 10) -> dict:
    with get_db() as conn:
        return sync_announcements(conn, days=days, max_pages=max_pages)


@app.get("/api/global-news", dependencies=[Depends(require_token)])
def api_global_news(limit: int = 50) -> dict:
    with get_db() as conn:
        return {"items": list_global_news(conn, limit=limit)}

@app.get("/api/announcements", dependencies=[Depends(require_token)])
def announcements_list(sec_code: str | None = None, limit: int = 50) -> dict:
    with get_db() as conn:
        return {"items": list_announcements(conn, sec_code=sec_code, limit=limit)}


@app.get("/api/rules/versions", dependencies=[Depends(require_token)])
def rule_versions() -> dict:
    lib = get_library()
    return {
        "versions": [
            {
                "version_code": v.version_code,
                "exchange": v.exchange,
                "doc_no": v.doc_no,
                "publish_date": v.publish_date.isoformat(),
                "effective_from": v.effective_from.isoformat(),
                "effective_to": v.effective_to.isoformat() if v.effective_to else None,
                "source_url": v.source_url,
                "boards": sorted(v.boards.keys()),
                "clauses": [c.model_dump() for c in v.clauses],
            }
            for v in lib.versions
        ]
    }


@app.get("/api/rules/resolve", dependencies=[Depends(require_token)])
def resolve_rule(
    exchange: str,
    board: str,
    date_str: str = Query(alias="date"),
    risk_flag: str = "NORMAL",
    listing_phase: str = "SEASONED",
) -> dict:
    try:
        d = date.fromisoformat(date_str)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"invalid date: {date_str}") from exc
    try:
        version, rules = get_library().select(exchange, board, risk_flag, listing_phase, d)  # type: ignore[arg-type]
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "version_code": version.version_code,
        "doc_no": version.doc_no,
        "source_url": version.source_url,
        "effective_from": version.effective_from.isoformat(),
        "effective_to": version.effective_to.isoformat() if version.effective_to else None,
        "rules": rules.model_dump(),
    }


@app.get("/api/calendar/{year_month}", dependencies=[Depends(require_token)])
def calendar_month(year_month: str) -> dict:
    if not re.fullmatch(r"\d{4}-\d{2}", year_month):
        raise HTTPException(status_code=422, detail="expected YYYY-MM")
    year, month = (int(x) for x in year_month.split("-"))
    with get_db() as conn:
        cal = TradingCalendar(conn)
        days = cal.month_days(year, month)
        coverage = cal.year_coverage(year)
    return {"month": year_month, "days": days, "coverage": coverage, "source": "szse_calendar"}


@app.post("/api/calendar/sync/{year_month}", dependencies=[Depends(require_token)])
def calendar_sync(year_month: str) -> dict:
    if not re.fullmatch(r"\d{4}-\d{2}", year_month):
        raise HTTPException(status_code=422, detail="expected YYYY-MM")
    year, month = (int(x) for x in year_month.split("-"))
    try:
        with get_db() as conn:
            cal = TradingCalendar(conn)
            count = cal.sync_month(year, month)
    except Exception as exc:  # network/parse failures must be explicit
        raise HTTPException(status_code=502, detail=f"calendar sync failed: {exc}") from exc
    return {"month": year_month, "synced": count, "source": "szse_calendar"}


@app.get("/api/rules/db/versions", dependencies=[Depends(require_token)])
def rule_db_versions() -> dict:
    with get_db() as conn:
        return {"versions": db_rule_versions(conn), **db_rule_stats(conn)}


@app.get("/api/securities/stats", dependencies=[Depends(require_token)])
def api_securities_stats() -> dict:
    with get_db() as conn:
        return securities_stats(conn)


@app.get("/api/securities", dependencies=[Depends(require_token)])
def api_securities(
    exchange: str | None = None,
    board: str | None = None,
    limit: int = 100,
) -> dict:
    with get_db() as conn:
        return {"items": list_securities(conn, exchange=exchange, board=board, limit=limit)}


@app.post("/api/securities/sync/{exchange}", dependencies=[Depends(require_token)])
def api_securities_sync(exchange: str, max_pages: int | None = None) -> dict:
    """Sync one exchange's security master from its registered source.

    SZSE requires ~146 pages (~1-2 min) and accepts max_pages for partial syncs.
    """
    exchange = exchange.upper()
    try:
        if exchange == "SSE":
            records = fetch_sse()
        elif exchange == "SZSE":
            records = fetch_szse(max_pages=max_pages)
        elif exchange == "BSE":
            records = fetch_bse()
        else:
            raise HTTPException(status_code=422, detail="exchange must be SSE/SZSE/BSE")
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - official SZSE list is WAF-blocked sometimes
        if exchange != "SZSE":
            raise HTTPException(status_code=502, detail=f"securities sync failed: {exc}") from exc
        with get_db() as conn:
            ensure_data_source(conn)
            fallback = populate_from_quotes(conn, "SZSE")
            summary = securities_stats(conn)
        return {"exchange": exchange, "fallback": True, "official_error": str(exc), **fallback, "stats": summary}
    with get_db() as conn:
        count = upsert_securities(conn, records)
        summary = securities_stats(conn)
    return {"exchange": exchange, "upserted": count, "stats": summary}


def _ai_client(provider: str | None, model: str | None):
    try:
        return make_client(provider or os.environ.get("GAI_AI_PROVIDER", "ollama"), model)
    except AiUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/ai/status", dependencies=[Depends(require_token)])
def api_ai_status(provider: str | None = None, model: str | None = None) -> dict:
    client = _ai_client(provider, model)
    with get_db() as conn:
        status = ai_status(conn, client)
    return {"provider": provider or os.environ.get("GAI_AI_PROVIDER", "ollama"), **status}


@app.post("/api/ai/analyze", dependencies=[Depends(require_token)])
def api_ai_analyze(limit: int = 10, provider: str | None = None, model: str | None = None) -> dict:
    client = _ai_client(provider, model)
    try:
        if hasattr(client, "available") and not client.available():
            raise AiUnavailable("configured AI backend is not available")
        with get_db() as conn:
            return analyze_pending(conn, client, limit=limit, model_id=model or getattr(client.config, "model", None))
    except AiUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/ai/analysis", dependencies=[Depends(require_token)])
def api_ai_analysis(limit: int = 50) -> dict:
    with get_db() as conn:
        return {"items": list_analysis(conn, limit=limit)}


@app.get("/api/alerts", dependencies=[Depends(require_token)])
def api_alerts(level: str | None = None, limit: int = 50) -> dict:
    with get_db() as conn:
        return {"items": list_alerts(conn, level=level, limit=limit)}


@app.post("/api/alerts/{alert_id}/ack", dependencies=[Depends(require_token)])
def api_alert_ack(alert_id: int) -> dict:
    with get_db() as conn:
        ok = acknowledge_alert(conn, alert_id)
    if not ok:
        raise HTTPException(status_code=404, detail="alert not found or already acknowledged")
    return {"ok": True, "alert_id": alert_id}


@app.get("/api/scheduler/jobs", dependencies=[Depends(require_token)])
def api_scheduler_jobs() -> dict:
    from .workers import build_scheduler

    sched = build_scheduler(get_db)
    return {"jobs": [{"id": job.id, "next_run_time": (getattr(job, "next_run_time", None).isoformat() if getattr(job, "next_run_time", None) else None)} for job in sched.get_jobs()]}


@app.post("/api/scheduler/trigger/{name}", dependencies=[Depends(require_token)])
def api_scheduler_trigger(name: str) -> dict:
    allowed = {"quotes", "news", "announcements", "calendar"}
    if name not in allowed:
        raise HTTPException(status_code=422, detail=f"job must be one of {sorted(allowed)}")
    try:
        run_job_now(get_db, name)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"ok": True, "job": name}


class WatchlistItemIn(BaseModel):
    code: str
    note: str | None = None


class ScreeningIn(BaseModel):
    filters: dict = {}


@app.get("/api/watchlist", dependencies=[Depends(require_token)])
def api_watchlist() -> dict:
    with get_db() as conn:
        ensure_default_watchlist(conn)
        lists = list_watchlists(conn)
        default = lists[0] if lists else None
        items = list_items(conn, default["id"]) if default else []
    return {"watchlists": lists, "items": items}


@app.post("/api/watchlist/items", dependencies=[Depends(require_token)])
def api_watchlist_add(payload: WatchlistItemIn) -> dict:
    with get_db() as conn:
        wid = ensure_default_watchlist(conn)
        try:
            added = add_item(conn, wid, payload.code, payload.note)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True, "added": added, "code": payload.code}


@app.delete("/api/watchlist/items/{code}", dependencies=[Depends(require_token)])
def api_watchlist_remove(code: str) -> dict:
    with get_db() as conn:
        wid = ensure_default_watchlist(conn)
        removed = remove_item(conn, wid, code)
    if not removed:
        raise HTTPException(status_code=404, detail="not in watchlist")
    return {"ok": True, "code": code}


@app.get("/api/signals", dependencies=[Depends(require_token)])
def api_signals(limit: int = 50) -> dict:
    with get_db() as conn:
        return {"items": list_signals(conn, limit=limit)}


@app.post("/api/signals/run", dependencies=[Depends(require_token)])
def api_signals_run() -> dict:
    with get_db() as conn:
        return run_signals(conn)


@app.post("/api/screening/run", dependencies=[Depends(require_token)])
def api_screening_run(payload: ScreeningIn | None = None) -> dict:
    with get_db() as conn:
        return run_screening(conn, filters=(payload.filters if payload else None))


@app.get("/api/screening/latest", dependencies=[Depends(require_token)])
def api_screening_latest() -> dict:
    with get_db() as conn:
        result = latest_run(conn)
    return result or {"run": None, "items": []}


class KlineSyncIn(BaseModel):
    codes: list[str]
    start: str
    end: str


class BacktestIn(BaseModel):
    codes: list[str]
    start_date: str
    end_date: str
    initial_cash: float = 1_000_000.0
    entry_pct: float = 5.0
    hold_days: int = 3
    max_positions: int = 5


class PaperOrderIn(BaseModel):
    code: str
    side: str
    qty: int
    order_type: str = "MARKET"
    price: float | None = None


class PredictionIn(BaseModel):
    code: str
    direction: str
    horizon_days: int = 5
    confidence: float | None = None
    model_id: str | None = None


@app.post("/api/klines/sync", dependencies=[Depends(require_token)])
def api_klines_sync(payload: KlineSyncIn) -> dict:
    with get_db() as conn:
        pairs: list[tuple[str, str]] = []
        missing: list[str] = []
        for code in payload.codes:
            row = conn.execute("SELECT exchange FROM securities WHERE code = ?", (code,)).fetchone()
            if row:
                pairs.append((code, row["exchange"]))
            else:
                missing.append(code)
        if not pairs:
            raise HTTPException(status_code=422, detail=f"securities not found: {missing}")
        try:
            result = sync_daily(conn, pairs, date.fromisoformat(payload.start), date.fromisoformat(payload.end))
            result["missing"] = missing
            return result
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/backtest/run", dependencies=[Depends(require_token)])
def api_backtest_run(payload: BacktestIn) -> dict:
    with get_db() as conn:
        return run_backtest(
            conn, payload.codes, payload.start_date, payload.end_date,
            initial_cash=payload.initial_cash, entry_pct=payload.entry_pct,
            hold_days=payload.hold_days, max_positions=payload.max_positions,
        )


@app.get("/api/backtest/{backtest_id}", dependencies=[Depends(require_token)])
def api_backtest_get(backtest_id: int) -> dict:
    with get_db() as conn:
        result = get_backtest(conn, backtest_id)
    if result is None:
        raise HTTPException(status_code=404, detail="backtest not found")
    return result


@app.get("/api/paper/account", dependencies=[Depends(require_token)])
def api_paper_account() -> dict:
    with get_db() as conn:
        return get_account(conn)


@app.post("/api/paper/orders", dependencies=[Depends(require_token)])
def api_paper_order(payload: PaperOrderIn) -> dict:
    with get_db() as conn:
        return place_order(conn, payload.code, payload.side, payload.qty, payload.order_type, payload.price)


@app.get("/api/paper/orders", dependencies=[Depends(require_token)])
def api_paper_orders(limit: int = 50) -> dict:
    with get_db() as conn:
        return {"items": paper_orders(conn, limit=limit)}


@app.get("/api/paper/trades", dependencies=[Depends(require_token)])
def api_paper_trades(limit: int = 50) -> dict:
    with get_db() as conn:
        return {"items": paper_trades(conn, limit=limit)}


@app.post("/api/paper/reset", dependencies=[Depends(require_token)])
def api_paper_reset() -> dict:
    with get_db() as conn:
        return reset_account(conn)


@app.get("/api/predictions", dependencies=[Depends(require_token)])
def api_predictions(limit: int = 50) -> dict:
    with get_db() as conn:
        return {"items": list_predictions(conn, limit=limit)}


@app.post("/api/predictions", dependencies=[Depends(require_token)])
def api_prediction_create(payload: PredictionIn) -> dict:
    with get_db() as conn:
        try:
            return create_prediction(conn, payload.code, payload.direction, payload.horizon_days,
                                     payload.confidence, payload.model_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/predictions/settle", dependencies=[Depends(require_token)])
def api_predictions_settle() -> dict:
    with get_db() as conn:
        return settle_predictions(conn)


@app.get("/api/accuracy", dependencies=[Depends(require_token)])
def api_accuracy() -> dict:
    with get_db() as conn:
        return accuracy(conn)


@app.post("/api/ai/stock-links/refresh", dependencies=[Depends(require_token)])
def api_ai_stock_links() -> dict:
    with get_db() as conn:
        return sync_stock_links(conn)


@app.post("/api/ai/recommendations/run", dependencies=[Depends(require_token)])
def api_ai_recommendations_run(provider: str | None = None, model: str | None = None) -> dict:
    """Aggregate evidence-linked buy candidates and holding advice.

    Source analyses are AI-generated; this step is deterministic so it cannot
    invent news, prices or financial numbers. Missing evidence yields no reco.
    """
    model_id = f"{provider or 'local'}:{model}" if (provider or model) else "evidence-aggregator"
    with get_db() as conn:
        return run_recommendations(conn, model_id=model_id)


@app.get("/api/ai/recommendations", dependencies=[Depends(require_token)])
def api_ai_recommendations(reco_type: str | None = None, limit: int = 100) -> dict:
    with get_db() as conn:
        return {"items": list_recommendations(conn, reco_type=reco_type, limit=limit)}


@app.get("/api/ai/recommendations/{reco_id}", dependencies=[Depends(require_token)])
def api_ai_recommendation_detail(reco_id: int) -> dict:
    with get_db() as conn:
        item = get_recommendation(conn, reco_id)
    if not item:
        raise HTTPException(status_code=404, detail="recommendation not found")
    return item


class AiKeyIn(BaseModel):
    provider: str = "deepseek"
    key: str


@app.post("/api/settings/ai-key", dependencies=[Depends(require_token)])
def api_set_ai_key(payload: AiKeyIn) -> dict:
    """Store an API key with Windows DPAPI (never returned, never logged)."""
    provider = payload.provider.lower()
    if provider not in ("deepseek", "ollama"):
        raise HTTPException(status_code=422, detail="provider must be deepseek/ollama")
    set_secret(f"{provider}_api_key", payload.key.strip())
    return {"ok": True, "provider": provider}


@app.get("/api/market/regime", dependencies=[Depends(require_token)])
def api_market_regime() -> dict:
    with get_db() as conn:
        return market_regime(conn)


@app.post("/api/trade-plans/run", dependencies=[Depends(require_token)])
def api_trade_plans_run(model: str | None = None) -> dict:
    with get_db() as conn:
        return build_trade_plans(conn, model_id=model or "evidence-aggregator")


@app.get("/api/trade-plans", dependencies=[Depends(require_token)])
def api_trade_plans(limit: int = 100) -> dict:
    with get_db() as conn:
        plans = list_trade_plans(conn, limit=limit)
        recos = list_recommendations(conn)
        run = conn.execute("SELECT id, model_id, created_at FROM recommendation_runs ORDER BY id DESC LIMIT 1").fetchone()
        latest_plan = conn.execute("SELECT MAX(created_at) AS t FROM ai_trade_plans WHERE status!='SUPERSEDED'").fetchone()
        return {
            "items": plans,
            "recos": recos,
            "meta": {
                "reco_run_id": run["id"] if run else None,
                "reco_model": run["model_id"] if run else None,
                "reco_created_at": run["created_at"] if run else None,
                "plan_created_at": latest_plan["t"] if latest_plan else None,
            },
        }


@app.post("/api/weekly/start", dependencies=[Depends(require_token)])
def api_weekly_start(initial_cash: float = 100000.0) -> dict:
    with get_db() as conn:
        return start_weekly_sim(conn, initial_cash=initial_cash)


@app.post("/api/weekly/evaluate", dependencies=[Depends(require_token)])
def api_weekly_evaluate() -> dict:
    with get_db() as conn:
        return evaluate_weekly(conn, fetch=True)

@app.get("/api/weekly/latest", dependencies=[Depends(require_token)])
def api_weekly_latest() -> dict:
    with get_db() as conn:
        return latest_weekly_sim(conn) or {"sim": None}


@app.exception_handler(Exception)
async def unhandled(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})












