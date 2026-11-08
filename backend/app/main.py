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
from fastapi.responses import JSONResponse

from .datasources.securities_lists import fetch_bse, fetch_sse, fetch_szse
from .db.migrate import migrate
from .rules import get_library
from .rules.store import list_versions as db_rule_versions, stats as db_rule_stats, sync_library
from .securities import list_securities, stats as securities_stats, upsert_securities
from .trading_calendar import TradingCalendar

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


@app.get("/api/dashboard", dependencies=[Depends(require_token)])
def dashboard() -> dict:
    cards = [
        "sse_index", "szse_index", "chinext_index", "star50", "bse50",
        "market_overview", "breadth", "limit_counts", "turnover",
        "good_news", "risk_alerts", "ai_opportunities",
        "watchlist", "signals", "paper_account",
    ]
    return {
        "cards": [
            {"key": k, "value": None, "status": "unavailable", "reason": "data_source_not_connected", "provenance": None}
            for k in cards
        ],
        "time": now_iso(),
    }


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
    if exchange == "SSE":
        records = fetch_sse()
    elif exchange == "SZSE":
        records = fetch_szse(max_pages=max_pages)
    elif exchange == "BSE":
        records = fetch_bse()
    else:
        raise HTTPException(status_code=422, detail="exchange must be SSE/SZSE/BSE")
    with get_db() as conn:
        count = upsert_securities(conn, records)
        summary = securities_stats(conn)
    return {"exchange": exchange, "upserted": count, "stats": summary}


@app.exception_handler(Exception)
async def unhandled(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})
