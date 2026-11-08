from __future__ import annotations

import pytest

from backend.app.rules.fees import calc_fees, limit_down_price, limit_up_price


def fee_set(library, exchange="SSE", board="MAIN", day="2026-11-08"):
    from datetime import date

    _, rules = library.select(exchange, board, "NORMAL", "SEASONED", date.fromisoformat(day))
    return rules.fees


def test_sse_sell_fees_exact(library):
    fees = fee_set(library)
    result = calc_fees(100_000, "SELL", fees, commission_rate=None)
    assert result.stamp_duty == pytest.approx(50.00)
    assert result.transfer_fee == pytest.approx(1.00)
    assert result.handling_fee == pytest.approx(3.41)
    assert result.regulatory_fee == pytest.approx(2.00)
    assert result.commission == 0.0
    assert result.total == pytest.approx(56.41)


def test_stamp_duty_only_on_sell(library):
    fees = fee_set(library)
    buy = calc_fees(100_000, "BUY", fees)
    assert buy.stamp_duty == 0.0
    assert buy.total == pytest.approx(6.41)


def test_commission_minimum(library):
    fees = fee_set(library)
    result = calc_fees(10_000, "BUY", fees, commission_rate=0.0003)
    assert result.commission == pytest.approx(5.0)


def test_commission_rate_applied(library):
    fees = fee_set(library)
    result = calc_fees(100_000, "BUY", fees, commission_rate=0.0003)
    assert result.commission == pytest.approx(30.0)


def test_bse_handling_fee(library):
    fees = fee_set(library, exchange="BSE", board="BSE")
    result = calc_fees(100_000, "SELL", fees)
    assert result.handling_fee == pytest.approx(12.50)
    assert result.stamp_duty == pytest.approx(50.00)
    assert result.transfer_fee == pytest.approx(1.00)


def test_2023_early_fee_rates(library):
    fees = fee_set(library, day="2023-03-01")
    result = calc_fees(100_000, "SELL", fees)
    assert result.stamp_duty == pytest.approx(100.00)
    assert result.handling_fee == pytest.approx(4.87)


def test_limit_price_rounding(library):
    assert limit_up_price(10.00, 0.10) == 11.00
    assert limit_down_price(10.00, 0.10) == 9.00
    assert limit_up_price(10.05, 0.10) == 11.06  # 11.055 half-up
    assert limit_down_price(10.05, 0.10) == 9.05  # 9.045 half-up


def test_invalid_amount():
    from backend.app.rules.models import Fees

    with pytest.raises(ValueError):
        calc_fees(0, "BUY", Fees())
