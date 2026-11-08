from __future__ import annotations

from datetime import date

import pytest

from backend.app.rules.loader import RuleNotFound


def test_library_has_all_versions(library):
    codes = {v.version_code for v in library.versions}
    assert len(library.versions) == 10
    for expected in [
        "SSE-2023.02.17", "SSE-2023.08.28", "SSE-2026.07.06",
        "SZSE-2023.02.17", "SZSE-2023.08.28", "SZSE-2026.07.06",
        "BSE-2021.11.15", "BSE-2023.08.28", "BSE-2026.07.06", "BSE-2026.08.31",
    ]:
        assert expected in codes


@pytest.mark.parametrize(
    ("exchange", "board", "risk", "day", "expected_version", "expected_pct"),
    [
        ("SSE", "MAIN", "ST", date(2026, 7, 3), "SSE-2023.08.28", 0.05),
        ("SSE", "MAIN", "ST", date(2026, 7, 6), "SSE-2026.07.06", 0.10),
        ("SZSE", "MAIN", "ST", date(2026, 7, 3), "SZSE-2023.08.28", 0.05),
        ("SZSE", "MAIN", "ST", date(2026, 7, 6), "SZSE-2026.07.06", 0.10),
        ("SSE", "MAIN", "NORMAL", date(2026, 11, 8), "SSE-2026.07.06", 0.10),
        ("SSE", "STAR", "NORMAL", date(2026, 11, 8), "SSE-2026.07.06", 0.20),
        ("SSE", "STAR", "ST", date(2026, 11, 8), "SSE-2026.07.06", 0.20),
        ("SZSE", "CHINEXT", "ST", date(2026, 11, 8), "SZSE-2026.07.06", 0.20),
        ("BSE", "BSE", "NORMAL", date(2026, 11, 8), "BSE-2026.08.31", 0.30),
        ("BSE", "BSE", "ST", date(2026, 11, 8), "BSE-2026.08.31", 0.30),
    ],
)
def test_effective_rule_selection(library, exchange, board, risk, day, expected_version, expected_pct):
    version, rules = library.select(exchange, board, risk, "SEASONED", day)
    assert version.version_code == expected_version
    assert rules.price_limit.up_pct == pytest.approx(expected_pct)
    assert rules.price_limit.down_pct == pytest.approx(expected_pct)


def test_no_rule_before_history(library):
    with pytest.raises(RuleNotFound):
        library.select("SSE", "MAIN", "NORMAL", "SEASONED", date(2022, 1, 4))


def test_unknown_board_raises(library):
    with pytest.raises(RuleNotFound):
        library.select("SSE", "CHINEXT", "NORMAL", "SEASONED", date(2026, 11, 8))


def test_listing_phase_fallback(library):
    # SSE main IPO day 2-5 uses the explicit IPO_DAY2_5 set (10%), not the first-day special.
    _, rules = library.select("SSE", "MAIN", "NORMAL", "IPO_DAY2_5", date(2026, 11, 8))
    assert rules.price_limit.type == "PCT"

    _, rules = library.select("SSE", "STAR", "NORMAL", "IPO_DAY1", date(2026, 11, 8))
    assert rules.price_limit.type == "NONE"


def test_bse_after_hours_pending(library):
    _, rules = library.select("BSE", "BSE", "NORMAL", "SEASONED", date(2026, 11, 8))
    assert rules.sessions.after_hours.enabled is False
    assert rules.sessions.after_hours.status == "PENDING"


def test_bse_risk_warning_cap_switch(library):
    _, before = library.select("BSE", "BSE", "ST", "SEASONED", date(2026, 8, 30))
    _, after = library.select("BSE", "BSE", "ST", "SEASONED", date(2026, 8, 31))
    assert before.risk_warning_buy_daily_cap is None
    assert after.risk_warning_buy_daily_cap == 200_000


def test_main_board_risk_warning_cap_preserved(library):
    _, rules = library.select("SSE", "MAIN", "ST", "SEASONED", date(2026, 7, 6))
    assert rules.risk_warning_buy_daily_cap == 500_000
