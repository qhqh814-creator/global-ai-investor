from __future__ import annotations

from datetime import datetime

from backend.app.workers.scheduler import (
    JOB_ANNOUNCEMENTS,
    JOB_AUTO_BUY,
    JOB_CALENDAR,
    JOB_NEWS,
    JOB_PIPELINE,
    JOB_QUOTES,
    JOB_RISK,
    build_scheduler,
    is_trading_session,
    run_job_now,
)


class FakeCalendar:
    def __init__(self, trading: bool):
        self.trading = trading

    def is_trading_day(self, day):
        return self.trading


def test_trading_session_boundaries():
    cal = FakeCalendar(True)
    assert is_trading_session(datetime(2026, 11, 9, 9, 30), cal) is True
    assert is_trading_session(datetime(2026, 11, 9, 9, 14), cal) is False
    assert is_trading_session(datetime(2026, 11, 9, 15, 35), cal) is True
    assert is_trading_session(datetime(2026, 11, 9, 15, 36), cal) is False
    assert is_trading_session(datetime(2026, 11, 8, 10, 0), FakeCalendar(False)) is False


def test_build_scheduler_registers_jobs():
    sched = build_scheduler(lambda: None)
    ids = {job.id for job in sched.get_jobs()}
    assert ids == {JOB_QUOTES, JOB_NEWS, JOB_ANNOUNCEMENTS, JOB_CALENDAR, JOB_PIPELINE, JOB_AUTO_BUY, JOB_RISK}


def test_run_job_now_unknown_raises():
    try:
        run_job_now(lambda: None, "does-not-exist")
        assert False, "expected KeyError"
    except KeyError:
        pass
