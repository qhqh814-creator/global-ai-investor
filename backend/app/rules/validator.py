"""Order validation against the effective rule set (P1).

Every check references RuleSet values; no business thresholds are hard-coded.
Errors are stable codes so tests and UI can translate them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from .models import RuleSet, RuleVersion

Session = Literal["OPEN_AUCTION", "CONTINUOUS", "CLOSE_AUCTION", "AFTER_HOURS"]
Side = Literal["BUY", "SELL"]
OrderType = Literal["LIMIT", "MARKET"]


@dataclass
class OrderRequest:
    exchange: str
    board: str
    security_code: str
    side: Side
    qty: int
    order_type: OrderType = "LIMIT"
    price: float | None = None
    session: Session = "CONTINUOUS"
    prev_close: float | None = None
    issue_price: float | None = None
    position_qty: int | None = None
    position_sellable: int | None = None
    risk_warning_bought_today: int = 0
    best_bid: float | None = None
    best_ask: float | None = None
    last_price: float | None = None


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    rule_version_id: str | None = None


def _round2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _tick_multiple(value: float, tick: float) -> bool:
    d = Decimal(str(value))
    t = Decimal(str(tick))
    return (d / t) == (d / t).to_integral_value()


def validate_order(order: OrderRequest, version: RuleVersion, rules: RuleSet) -> ValidationResult:
    errors: list[str] = []

    # ---- quantity -----------------------------------------------------
    params = rules.order
    if order.qty <= 0:
        errors.append("QTY_INVALID")
    if order.side == "BUY":
        if order.qty < params.min_qty:
            errors.append("QTY_BELOW_MIN")
        if params.multiple_required:
            if order.qty % params.step != 0:
                errors.append("QTY_NOT_MULTIPLE")
        else:
            if (order.qty - params.min_qty) % params.step != 0:
                errors.append("QTY_STEP_INVALID")
    else:
        # Selling: the 100-share multiple rule targets buys; an odd-lot remainder
        # may be sold in one order (validated below via position_qty).
        if order.qty < params.min_qty and order.qty != order.position_qty:
            errors.append("QTY_BELOW_MIN")

    if order.session == "AFTER_HOURS":
        ah = rules.sessions.after_hours
        if not ah.enabled or ah.status == "PENDING":
            errors.append("AFTER_HOURS_DISABLED")
        else:
            if order.qty < ah.min_qty:
                errors.append("QTY_BELOW_MIN")
            if (order.qty - ah.min_qty) % ah.step != 0:
                errors.append("QTY_STEP_INVALID")
            if order.qty > ah.max_qty:
                errors.append("QTY_ABOVE_MAX")
            if order.order_type != "LIMIT":
                errors.append("AFTER_HOURS_LIMIT_ONLY")
    else:
        cap = params.max_qty_market if order.order_type == "MARKET" and params.max_qty_market else params.max_qty
        if order.qty > cap:
            errors.append("QTY_ABOVE_MAX")

    # ---- price tick ---------------------------------------------------
    if order.order_type == "LIMIT":
        if order.price is None:
            errors.append("PRICE_REQUIRED")
        elif not _tick_multiple(order.price, rules.tick_size):
            errors.append("PRICE_TICK_INVALID")

    # ---- price limit --------------------------------------------------
    lim = rules.price_limit
    if order.order_type == "LIMIT" and order.price is not None:
        if lim.type == "PCT":
            base = order.prev_close
            if base is None:
                errors.append("MISSING_BASE_PRICE")
            else:
                up = float(_round2(Decimal(str(base)) * (1 + Decimal(str(lim.up_pct)))))
                down = float(_round2(Decimal(str(base)) * (1 - Decimal(str(lim.down_pct)))))
                if order.price > up or order.price < down:
                    errors.append("PRICE_LIMIT_VIOLATION")
        elif lim.type == "FIRST_DAY_SPECIAL":
            base = order.issue_price if lim.base_price_type == "ISSUE_PRICE" else order.prev_close
            if base is None:
                errors.append("MISSING_BASE_PRICE")
            else:
                if order.session == "OPEN_AUCTION":
                    lo = float(_round2(Decimal(str(base)) * Decimal(str(lim.first_day_auction_min_ratio))))
                    hi = float(_round2(Decimal(str(base)) * Decimal(str(lim.first_day_auction_max_ratio))))
                else:
                    lo = float(_round2(Decimal(str(base)) * Decimal(str(lim.first_day_continuous_min_ratio))))
                    hi = float(_round2(Decimal(str(base)) * Decimal(str(lim.first_day_continuous_max_ratio))))
                if order.price > hi or order.price < lo:
                    errors.append("PRICE_LIMIT_VIOLATION")

    # ---- price cage (continuous auction limit orders) -----------------
    cage = rules.price_cage
    if (
        cage.enabled
        and order.order_type == "LIMIT"
        and order.price is not None
        and order.session in cage.applies_sessions
    ):
        base = order.best_ask if order.side == "BUY" else order.best_bid
        if base is None:
            base = order.last_price if order.last_price is not None else order.prev_close
        if base is not None and base > 0:
            if order.side == "BUY":
                pct_bound = Decimal(str(base)) * (1 + Decimal(str(cage.pct or 0)))
                abs_bound = None
                if cage.abs_offset is not None:
                    abs_bound = Decimal(str(base)) + Decimal(str(cage.abs_offset))
                elif cage.abs_ticks is not None:
                    abs_bound = Decimal(str(base)) + Decimal(str(cage.abs_ticks)) * Decimal(str(rules.tick_size))
                bound = max(pct_bound, abs_bound) if abs_bound is not None else pct_bound
                if Decimal(str(order.price)) > _round2(bound):
                    errors.append("PRICE_CAGE_VIOLATION")
            else:
                pct_bound = Decimal(str(base)) * (1 - Decimal(str(cage.pct or 0)))
                abs_bound = None
                if cage.abs_offset is not None:
                    abs_bound = Decimal(str(base)) - Decimal(str(cage.abs_offset))
                elif cage.abs_ticks is not None:
                    abs_bound = Decimal(str(base)) - Decimal(str(cage.abs_ticks)) * Decimal(str(rules.tick_size))
                bound = min(pct_bound, abs_bound) if abs_bound is not None else pct_bound
                if Decimal(str(order.price)) < _round2(bound):
                    errors.append("PRICE_CAGE_VIOLATION")

    # ---- T+1 sellable -------------------------------------------------
    if order.side == "SELL" and order.position_sellable is not None:
        if order.qty > order.position_sellable:
            errors.append("T1_NOT_SELLABLE")

    # ---- odd lot ------------------------------------------------------
    if order.side == "SELL" and order.position_qty is not None:
        if order.qty % rules.order.odd_lot_threshold != 0:
            # sub-threshold remainder must be sold in one order
            if order.qty != order.position_qty:
                errors.append("ODD_LOT_NOT_ONE_ORDER")

    # ---- risk warning daily buy cap -----------------------------------
    if order.side == "BUY" and rules.risk_warning_buy_daily_cap is not None:
        if order.risk_warning_bought_today + order.qty > rules.risk_warning_buy_daily_cap:
            errors.append("RISK_WARNING_DAILY_CAP")

    return ValidationResult(ok=not errors, errors=errors, rule_version_id=version.version_code)
