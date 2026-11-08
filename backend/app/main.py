"""Global AI Investor V1.0 backend (FastAPI sidecar).

P0 skeleton: health check, status endpoint, SQLite bootstrap.
Business modules (datasources/rules/analysis/backtest) are added in P1+.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

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
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db() -> None:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL,
                checksum TEXT
            );
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            INSERT OR IGNORE INTO schema_migrations(version, applied_at, checksum)
                VALUES ('0001_init', datetime('now'), 'p0-skeleton');
            """
        )
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO app_settings(key, value_json, updated_at) VALUES (?, ?, ?)",
            ("app.last_start", json.dumps({"started_at": now_iso()}), now_iso()),
        )


async def require_token(request: Request) -> None:
    if not TOKEN:
        return
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {TOKEN}":
        raise HTTPException(status_code=401, detail="unauthorized")


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "gai-backend",
        "version": "0.1.0",
        "port": PORT,
        "time": now_iso(),
    }


@app.get("/api/status", dependencies=[Depends(require_token)])
def status() -> dict:
    init_db()
    with get_db() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM schema_migrations").fetchone()
        migrations = int(row["c"]) if row else 0
    return {
        "ok": True,
        "root": str(ROOT),
        "db": str(DB_PATH),
        "migrations": migrations,
        "time": now_iso(),
    }


@app.get("/api/dashboard", dependencies=[Depends(require_token)])
def dashboard() -> dict:
    """P0: every card is explicitly 'unavailable' with a reason.

    P2 will fill real values with provenance; unavailable entries must stay
    unavailable rather than showing fabricated numbers.
    """
    cards = [
        "sse_index",
        "szse_index",
        "chinext_index",
        "star50",
        "bse50",
        "market_overview",
        "breadth",
        "limit_counts",
        "turnover",
        "good_news",
        "risk_alerts",
        "ai_opportunities",
        "watchlist",
        "signals",
        "paper_account",
    ]
    return {
        "cards": [
            {
                "key": key,
                "value": None,
                "status": "unavailable",
                "reason": "data_source_not_connected",
                "provenance": None,
            }
            for key in cards
        ],
        "time": now_iso(),
    }


@app.exception_handler(Exception)
async def unhandled(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})
