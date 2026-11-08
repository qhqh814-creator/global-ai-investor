"""Daily K-line adapter (Eastmoney push2his, P2/P5).

Verified format: data.klines entries are
"date,open,close,high,low,volume,amount,amplitude,pct,change,turnover".
Unlicensed third-party snapshot; used for local backtest/research only.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date

import httpx

SOURCE_ID = "eastmoney_kline"
KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
HEADERS = {"User-Agent": "GlobalAIInvestor/0.1 (personal research)"}


@dataclass(frozen=True)
class DailyBar:
    code: str
    trade_date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float
    change_pct: float


def secid(code: str, exchange: str) -> str:
    return f"{'1' if exchange == 'SSE' else '0'}.{code}"


def parse_klines(code: str, klines: list[str]) -> list[DailyBar]:
    bars: list[DailyBar] = []
    for line in klines:
        parts = line.split(",")
        if len(parts) < 10:
            continue
        try:
            bars.append(
                DailyBar(
                    code=code,
                    trade_date=parts[0],
                    open=float(parts[1]),
                    close=float(parts[2]),
                    high=float(parts[3]),
                    low=float(parts[4]),
                    volume=float(parts[5]),
                    amount=float(parts[6]),
                    change_pct=float(parts[8]),
                )
            )
        except ValueError:
            continue
    return bars


def fetch_daily(code: str, exchange: str, start: date, end: date, adjust: int = 0) -> list[DailyBar]:
    params = {
        "secid": secid(code, exchange),
        "klt": "101",
        "fqt": str(adjust),
        "beg": start.strftime("%Y%m%d"),
        "end": end.strftime("%Y%m%d"),
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
    }
    last_exc: Exception | None = None
    for attempt in range(4):
        try:
            with httpx.Client(timeout=45.0, follow_redirects=True) as client:
                resp = client.get(KLINE_URL, params=params, headers=HEADERS)
                resp.raise_for_status()
                payload = resp.json()
            data = payload.get("data") or {}
            return parse_klines(code, data.get("klines") or [])
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            time.sleep(1 + 2**attempt)
    raise RuntimeError(f"kline fetch failed for {code}") from last_exc
