"""Rule library domain models (P1).

All trading rules are data, never hard-coded. Missing rules raise RuleNotFound
instead of silently falling back to a default (e.g. 10%).
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

RiskFlag = Literal["NORMAL", "ST", "DELISTING"]
ListingPhase = Literal["IPO_DAY1", "IPO_DAY2_5", "SEASONED"]
Exchange = Literal["SSE", "SZSE", "BSE"]
Board = Literal["MAIN", "STAR", "CHINEXT", "BSE"]


class PriceLimit(BaseModel):
    type: Literal["PCT", "NONE", "FIRST_DAY_SPECIAL"]
    up_pct: float | None = None
    down_pct: float | None = None
    first_day_up_pct: float | None = None
    first_day_down_pct: float | None = None
    first_day_auction_min_ratio: float | None = None
    first_day_auction_max_ratio: float | None = None
    first_day_continuous_min_ratio: float | None = None
    first_day_continuous_max_ratio: float | None = None
    rounding: Literal["HALF_UP_TO_0.01"] = "HALF_UP_TO_0.01"
    base_price_type: Literal["PREV_CLOSE", "ISSUE_PRICE", "EX_RIGHTS_PRICE"] = "PREV_CLOSE"

    @model_validator(mode="after")
    def _validate(self) -> "PriceLimit":
        if self.type == "PCT" and (self.up_pct is None or self.down_pct is None):
            raise ValueError("PCT price limit requires up_pct and down_pct")
        if self.type == "FIRST_DAY_SPECIAL":
            if self.first_day_auction_min_ratio is None or self.first_day_auction_max_ratio is None:
                raise ValueError("FIRST_DAY_SPECIAL requires auction ratio bounds")
        return self


class OrderParams(BaseModel):
    min_qty: int = Field(gt=0)
    step: int = Field(gt=0)
    multiple_required: bool
    max_qty: int = Field(gt=0)
    max_qty_market: int | None = None
    odd_lot_threshold: int = Field(gt=0)
    odd_lot_must_one_order: bool = True


class PriceCage(BaseModel):
    enabled: bool = True
    pct: float | None = None
    abs_offset: float | None = None
    abs_ticks: int | None = None
    compare: Literal["WIDER", "HIGHER_ONLY"] = "WIDER"
    applies_sessions: list[str] = Field(default_factory=lambda: ["CONTINUOUS"])


class Fees(BaseModel):
    stamp_duty: float = 0.0
    transfer_fee: float = 0.0
    handling_fee: float = 0.0
    regulatory_fee: float = 0.0
    commission_min: float = 5.0


class AfterHours(BaseModel):
    enabled: bool = False
    order: list[list[str]] = Field(default_factory=list)
    trade: list[str] = Field(default_factory=list)
    price: Literal["CLOSE"] = "CLOSE"
    min_qty: int = 100
    step: int = 100
    max_qty: int = 1_000_000
    status: Literal["EFFECTIVE", "PENDING"] = "EFFECTIVE"


class Sessions(BaseModel):
    open_auction: list[str]
    open_auction_cancel_cutoff: str = "09:20"
    continuous: list[list[str]]
    close_auction: list[str]
    after_hours: AfterHours = Field(default_factory=AfterHours)
    close_auction_cancel_allowed: bool = False


class RuleSet(BaseModel):
    risk_flag: RiskFlag
    listing_phase: ListingPhase
    price_limit: PriceLimit
    order: OrderParams
    tick_size: float = 0.01
    price_cage: PriceCage = Field(default_factory=PriceCage)
    fees: Fees = Field(default_factory=Fees)
    sessions: Sessions
    settlement: Literal["T+1", "T+0"] = "T+1"
    risk_warning_buy_daily_cap: int | None = None
    market_order_allowed: bool = True
    notes: list[str] = Field(default_factory=list)


class Clause(BaseModel):
    clause_no: str
    title: str
    status: Literal["EFFECTIVE", "PENDING"]
    note: str = ""


class BoardRules(BaseModel):
    sets: list[RuleSet]

    @model_validator(mode="after")
    def _unique(self) -> "BoardRules":
        seen = set()
        for rs in self.sets:
            key = (rs.risk_flag, rs.listing_phase)
            if key in seen:
                raise ValueError(f"duplicate rule set for {key}")
            seen.add(key)
        return self


class RuleVersion(BaseModel):
    version_code: str
    exchange: Exchange
    doc_no: str
    publish_date: date
    effective_from: date
    effective_to: date | None = None
    source_url: str
    supersedes: str | None = None
    checksum: str | None = None
    clauses: list[Clause] = Field(default_factory=list)
    boards: dict[str, BoardRules]

    def effective_on(self, on_date: date) -> bool:
        return self.effective_from <= on_date and (self.effective_to is None or on_date <= self.effective_to)

