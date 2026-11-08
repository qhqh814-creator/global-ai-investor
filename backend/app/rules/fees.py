"""Fee calculation (P1).

Rates come from the effective RuleSet; no hard-coded rates here.
Amounts are CNY; result rounded to cents (half-up).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from .models import Fees


@dataclass(frozen=True)
class FeeBreakdown:
    amount: float
    stamp_duty: float
    transfer_fee: float
    handling_fee: float
    regulatory_fee: float
    commission: float
    total: float

    def as_dict(self) -> dict:
        return {
            "amount": self.amount,
            "stamp_duty": self.stamp_duty,
            "transfer_fee": self.transfer_fee,
            "handling_fee": self.handling_fee,
            "regulatory_fee": self.regulatory_fee,
            "commission": self.commission,
            "total": self.total,
        }


def round_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calc_fees(
    amount: float,
    side: Literal["BUY", "SELL"],
    fees: Fees,
    commission_rate: float | None = None,
) -> FeeBreakdown:
    if amount <= 0:
        raise ValueError("amount must be positive")
    if side not in ("BUY", "SELL"):
        raise ValueError(f"invalid side: {side}")

    amt = Decimal(str(amount))
    stamp = round_money(amt * Decimal(str(fees.stamp_duty))) if side == "SELL" else Decimal("0.00")
    transfer = round_money(amt * Decimal(str(fees.transfer_fee)))
    handling = round_money(amt * Decimal(str(fees.handling_fee)))
    regulatory = round_money(amt * Decimal(str(fees.regulatory_fee)))

    commission = Decimal("0.00")
    if commission_rate is not None:
        commission = round_money(amt * Decimal(str(commission_rate)))
        if commission < Decimal(str(fees.commission_min)):
            commission = Decimal(str(fees.commission_min))

    total = stamp + transfer + handling + regulatory + commission
    return FeeBreakdown(
        amount=float(amt),
        stamp_duty=float(stamp),
        transfer_fee=float(transfer),
        handling_fee=float(handling),
        regulatory_fee=float(regulatory),
        commission=float(commission),
        total=float(total),
    )


def limit_up_price(prev_close: float, up_pct: float) -> float:
    return float(round_money(Decimal(str(prev_close)) * (1 + Decimal(str(up_pct)))))


def limit_down_price(prev_close: float, down_pct: float) -> float:
    return float(round_money(Decimal(str(prev_close)) * (1 - Decimal(str(down_pct)))))
