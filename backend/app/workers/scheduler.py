"""In-process scheduler (P2/P3).

Jobs are only started when GAI_ENABLE_SCHEDULER=1 (desktop mode). Tests import
the pure helpers without starting threads.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, time as dtime, timezone, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from ..content.service import sync_announcements, sync_news
from ..quotes.service import sync_quotes
from ..trading_calendar import TradingCalendar
from ..pipeline.service import run_pipeline
from ..auto_trade.service import auto_buy_ready, risk_check

TZ = timezone(timedelta(hours=8))
TRADING_START = dtime(9, 15)
TRADING_END = dtime(15, 35)

JOB_QUOTES = "quotes"
JOB_NEWS = "news"
JOB_ANNOUNCEMENTS = "announcements"
JOB_CALENDAR = "calendar"
JOB_PIPELINE = "pipeline"
JOB_AUTO_BUY = "auto_buy"
JOB_RISK = "risk_check"

_scheduler: BackgroundScheduler | None = None


def is_trading_session(now: datetime, calendar: TradingCalendar) -> bool:
    if now.tzinfo is None:
        now = now.replace(tzinfo=TZ)
    if calendar.is_trading_day(now.date()) is not True:
        return False
    t = now.timetz().replace(tzinfo=None)
    return TRADING_START <= t <= TRADING_END


def _log(conn, job: str, start: float, records: int, error: str | None) -> None:
    conn.execute(
        "INSERT INTO data_fetch_log(source_id, endpoint, status_code, duration_ms, records_count, error_code, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            f"scheduler:{job}",
            job,
            0 if error is None else 1,
            int((time.monotonic() - start) * 1000),
            records,
            error,
            datetime.now(TZ).isoformat(timespec="seconds"),
        ),
    )
    conn.commit()


def build_scheduler(conn_factory, scheduler: BackgroundScheduler | None = None) -> BackgroundScheduler:
    """Register jobs; caller decides whether to start()."""

    def quotes_job() -> None:
        start = time.monotonic()
        error = None
        records = 0
        with conn_factory() as conn:
            try:
                cal = TradingCalendar(conn)
                if not is_trading_session(datetime.now(TZ), cal):
                    _log(conn, JOB_QUOTES, start, 0, "skipped:not_trading_session")
                    return
                result = sync_quotes(conn)
                records = int(result.get("stocks") or 0) + int(result.get("indices") or 0)
            except Exception as exc:  # noqa: BLE001
                error = f"{type(exc).__name__}: {exc}"
            _log(conn, JOB_QUOTES, start, records, error)

    def news_job() -> None:
        start = time.monotonic()
        error = None
        records = 0
        with conn_factory() as conn:
            try:
                result = sync_news(conn)
                records = int(result.get("fetched") or 0)
                if result.get("errors"):
                    error = "; ".join(result["errors"])
            except Exception as exc:  # noqa: BLE001
                error = f"{type(exc).__name__}: {exc}"
            _log(conn, JOB_NEWS, start, records, error)

    def announcements_job() -> None:
        start = time.monotonic()
        error = None
        records = 0
        with conn_factory() as conn:
            try:
                result = sync_announcements(conn, days=1, max_pages=50)
                records = int(result.get("fetched") or 0)
                if result.get("error"):
                    error = str(result["error"])
            except Exception as exc:  # noqa: BLE001
                error = f"{type(exc).__name__}: {exc}"
            _log(conn, JOB_ANNOUNCEMENTS, start, records, error)

    def calendar_job() -> None:
        start = time.monotonic()
        error = None
        records = 0
        with conn_factory() as conn:
            try:
                cal = TradingCalendar(conn)
                today = datetime.now(TZ).date()
                records += cal.sync_month(today.year, today.month)
                month = today.month + 1
                year = today.year + (1 if month > 12 else 0)
                month = 1 if month > 12 else month
                records += cal.sync_month(year, month)
            except Exception as exc:  # noqa: BLE001
                error = f"{type(exc).__name__}: {exc}"
            _log(conn, JOB_CALENDAR, start, records, error)

    def pipeline_job() -> None:
        start = time.monotonic()
        error = None
        records = 0
        with conn_factory() as conn:
            try:
                cal = TradingCalendar(conn)
                comp = run_pipeline(conn, collect=True, days=1, max_pages=10, analyze_limit=12,
                                     provider="deepseek", model="deepseek-chat")
                records = len([s for s in comp.get("stages", []) if s.get("status") == "ok"])
            except Exception as exc:  # noqa: BLE001
                error = f"{type(exc).__name__}: {exc}"
            _log(conn, JOB_PIPELINE, start, records, error)

    def auto_buy_job() -> None:
        start = time.monotonic()
        error = None
        records = 0
        with conn_factory() as conn:
            try:
                cal = TradingCalendar(conn)
                if cal.is_trading_day(datetime.now(TZ).date()) is not True:
                    _log(conn, JOB_AUTO_BUY, start, 0, "skipped:not_trading_day")
                    return
                result = auto_buy_ready(conn)
                records = int(result.get("placed") or 0)
            except Exception as exc:  # noqa: BLE001
                error = f"{type(exc).__name__}: {exc}"
            _log(conn, JOB_AUTO_BUY, start, records, error)

    def risk_job() -> None:
        start = time.monotonic()
        error = None
        records = 0
        with conn_factory() as conn:
            try:
                cal = TradingCalendar(conn)
                if not is_trading_session(datetime.now(TZ), cal):
                    _log(conn, JOB_RISK, start, 0, "skipped:not_trading_session")
                    return
                result = risk_check(conn)
                records = int(result.get("sold") or 0)
            except Exception as exc:  # noqa: BLE001
                error = f"{type(exc).__name__}: {exc}"
            _log(conn, JOB_RISK, start, records, error)
    sched = scheduler or BackgroundScheduler(timezone=TZ)
    sched.add_job(quotes_job, "cron", minute="*/5", id=JOB_QUOTES, replace_existing=True)
    sched.add_job(news_job, "cron", minute="*/30", id=JOB_NEWS, replace_existing=True)
    sched.add_job(announcements_job, "cron", hour="18", minute="5", id=JOB_ANNOUNCEMENTS, replace_existing=True)
    sched.add_job(calendar_job, "cron", day="1", hour="9", minute="0", id=JOB_CALENDAR, replace_existing=True)
    sched.add_job(pipeline_job, "cron", day_of_week="mon-fri", hour="8", minute="30", id=JOB_PIPELINE, replace_existing=True)
    sched.add_job(auto_buy_job, "cron", day_of_week="mon-fri", hour="9", minute="35", id=JOB_AUTO_BUY, replace_existing=True)
    sched.add_job(risk_job, "cron", minute="0,30", hour="9-15", id=JOB_RISK, replace_existing=True)
    return sched


def start_scheduler(conn_factory) -> BackgroundScheduler | None:
    global _scheduler
    if os.environ.get("GAI_ENABLE_SCHEDULER") != "1":
        return None
    _scheduler = build_scheduler(conn_factory)
    _scheduler.start()
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def run_job_now(conn_factory, name: str) -> None:
    """Manually execute a registered job (used by the settings/status API)."""
    sched = build_scheduler(conn_factory)
    job = sched.get_job(name)
    if job is None:
        raise KeyError(f"unknown job: {name}")
    job.func()

