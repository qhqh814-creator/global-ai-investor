from __future__ import annotations

from datetime import date

from backend.app.rules.validator import OrderRequest, validate_order


def rules_for(library, exchange="SSE", board="MAIN", risk="NORMAL", day="2026-11-08", phase="SEASONED"):
    version, rules = library.select(exchange, board, risk, phase, date.fromisoformat(day))
    return version, rules


def order(**kwargs):
    base = dict(
        exchange="SSE",
        board="MAIN",
        security_code="600519",
        side="BUY",
        qty=100,
        order_type="LIMIT",
        price=10.0,
        session="CONTINUOUS",
        prev_close=10.0,
        best_bid=9.99,
        best_ask=10.01,
    )
    base.update(kwargs)
    return OrderRequest(**base)


def test_main_board_buy_100_multiple(library):
    version, rules = rules_for(library)
    result = validate_order(order(qty=150), version, rules)
    assert "QTY_NOT_MULTIPLE" in result.errors

    result = validate_order(order(qty=200), version, rules)
    assert result.ok, result.errors


def test_star_min_200_step_1(library):
    version, rules = rules_for(library, board="STAR")
    result = validate_order(order(board="STAR", qty=150), version, rules)
    assert "QTY_BELOW_MIN" in result.errors

    result = validate_order(order(board="STAR", qty=201), version, rules)
    assert result.ok, result.errors


def test_bse_min_100_step_1(library):
    version, rules = rules_for(library, exchange="BSE", board="BSE")
    result = validate_order(order(exchange="BSE", board="BSE", qty=150), version, rules)
    assert result.ok, result.errors


def test_odd_lot_must_be_sold_in_one_order(library):
    version, rules = rules_for(library)
    # holding 350, selling 150 -> invalid (leaves an odd lot that is not the whole position)
    result = validate_order(order(side="SELL", qty=150, position_qty=350, position_sellable=350), version, rules)
    assert "ODD_LOT_NOT_ONE_ORDER" in result.errors

    # selling the entire odd-lot remainder is allowed
    result = validate_order(order(side="SELL", qty=50, position_qty=50, position_sellable=50), version, rules)
    assert result.ok, result.errors


def test_t_plus_1_sellable(library):
    version, rules = rules_for(library)
    result = validate_order(order(side="SELL", qty=100, position_qty=100, position_sellable=0), version, rules)
    assert "T1_NOT_SELLABLE" in result.errors


def test_st_daily_buy_cap(library):
    version, rules = rules_for(library, risk="ST")
    result = validate_order(order(qty=500_001), version, rules)
    assert "RISK_WARNING_DAILY_CAP" in result.errors

    result = validate_order(order(qty=500_000), version, rules)
    assert result.ok, result.errors


def test_bse_st_cap_after_20260831(library):
    version, rules = rules_for(library, exchange="BSE", board="BSE", risk="ST", day="2026-08-31")
    result = validate_order(
        order(exchange="BSE", board="BSE", qty=200_001, price=10.0, best_ask=10.01),
        version,
        rules,
    )
    assert "RISK_WARNING_DAILY_CAP" in result.errors

    version, rules = rules_for(library, exchange="BSE", board="BSE", risk="ST", day="2026-08-30")
    result = validate_order(
        order(exchange="BSE", board="BSE", qty=200_001, price=10.0, best_ask=10.01),
        version,
        rules,
    )
    assert "RISK_WARNING_DAILY_CAP" not in result.errors


def test_price_limit_violation(library):
    version, rules = rules_for(library)
    result = validate_order(order(price=11.01, prev_close=10.0), version, rules)
    assert "PRICE_LIMIT_VIOLATION" in result.errors

    result = validate_order(order(price=9.0, prev_close=10.0), version, rules)
    assert result.ok, result.errors


def test_price_tick(library):
    version, rules = rules_for(library)
    result = validate_order(order(price=10.005), version, rules)
    assert "PRICE_TICK_INVALID" in result.errors


def test_price_cage_main_board(library):
    version, rules = rules_for(library)
    # best ask 10.00 -> buy bound max(10.20, 10.10) = 10.20
    result = validate_order(order(price=10.30, best_ask=10.00), version, rules)
    assert "PRICE_CAGE_VIOLATION" in result.errors

    result = validate_order(order(price=10.20, best_ask=10.00), version, rules)
    assert result.ok, result.errors


def test_price_cage_bse(library):
    version, rules = rules_for(library, exchange="BSE", board="BSE")
    # base 10.00 -> BSE buy bound max(10.50, 10.10) = 10.50
    result = validate_order(order(exchange="BSE", board="BSE", price=10.60, best_ask=10.00), version, rules)
    assert "PRICE_CAGE_VIOLATION" in result.errors


def test_after_hours_rules(library):
    version, rules = rules_for(library)
    result = validate_order(
        order(session="AFTER_HOURS", qty=100, price=10.0, prev_close=10.0, best_bid=None, best_ask=None), version, rules
    )
    assert result.ok, result.errors

    version, rules = rules_for(library, exchange="BSE", board="BSE")
    result = validate_order(
        order(exchange="BSE", board="BSE", session="AFTER_HOURS", qty=100, price=10.0), version, rules
    )
    assert "AFTER_HOURS_DISABLED" in result.errors


def test_new_stock_first_day(library):
    version, rules = rules_for(library, board="MAIN", phase="IPO_DAY1")
    # issue 10 -> continuous valid range 6.40..14.40
    result = validate_order(
        order(price=15.00, issue_price=10.0, prev_close=None, best_bid=None, best_ask=None), version, rules
    )
    assert "PRICE_LIMIT_VIOLATION" in result.errors

    result = validate_order(
        order(price=14.40, issue_price=10.0, prev_close=None, best_bid=None, best_ask=None), version, rules
    )
    assert result.ok, result.errors


def test_risk_warning_cap_none_for_star(library):
    version, rules = rules_for(library, board="STAR", risk="ST")
    assert rules.risk_warning_buy_daily_cap is None

