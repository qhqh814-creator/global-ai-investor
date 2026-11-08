"""Deep-exchange (SZSE) trading calendar adapter.

Official endpoint observed 2026-11-08:
  GET https://www.szse.cn/api/report/exchange/onepersistenthour/monthList?month=YYYY-MM
  -> {"data":[{"zrxh":1,"jybz":"0","jyrq":"2026-11-01"}, ...]}
  jybz == "1" => trading day, "0" => closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import httpx

SOURCE_ID = "szse_calendar"
BASE_URL = "https://www.szse.cn/api/report/exchange/onepersistenthour/monthList"


@dataclass(frozen=True)
class CalendarDay:
    trade_date: date
    is_trading_day: bool


def fetch_month(year: int, month: int, timeout: float = 30.0) -> list[CalendarDay]:
    params = {"month": f"{year:04d}-{month:02d}"}
    headers = {
        "Referer": "https://www.szse.cn/",
        "User-Agent": "GlobalAIInvestor/0.1 (personal research; contact: local)",
    }
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.get(BASE_URL, params=params, headers=headers)
        resp.raise_for_status()
        payload = resp.json()

    rows = payload.get("data")
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"unexpected SZSE calendar payload for {year}-{month:02d}")

    days: list[CalendarDay] = []
    for row in rows:
        raw = row.get("jyrq")
        flag = row.get("jybz")
        if not raw or flag not in ("0", "1"):
            raise ValueError(f"unexpected calendar row: {row!r}")
        days.append(CalendarDay(trade_date=date.fromisoformat(raw), is_trading_day=flag == "1"))
    return days
