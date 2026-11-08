"""Eastmoney quote adapter (P2, primary free source).

Status: unlicensed third-party snapshot (internal/demo use only). Never label
as real-time; provenance fields are attached to every record.

Indices: push2.eastmoney.com/api/qt/ulist.np/get
Stocks:  push2.eastmoney.com/api/qt/clist/get (100 rows/page; ~60 pages for A shares)
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx

SOURCE_ID = "eastmoney_quote"
QUOTE_KIND = "snapshot_unknown"
LICENSE_STATUS = "unlicensed_third_party"
COMMERCIAL_OK = False
TZ = timezone(timedelta(hours=8))

INDEX_SECIDS: dict[str, str] = {
    "000001": "1.000001",  # 上证指数
    "399001": "0.399001",  # 深证成指
    "399006": "0.399006",  # 创业板指
    "000688": "1.000688",  # 科创50
    "899050": "0.899050",  # 北证50
}

INDEX_ULIST_URL = "https://push2.eastmoney.com/api/qt/ulist.np/get"
STOCK_CLIST_URL = "https://push2.eastmoney.com/api/qt/clist/get"
MARKET_FS = "m:0+t:6,m:0+t:13,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"
HEADERS = {"User-Agent": "GlobalAIInvestor/0.1 (personal research)"}


@dataclass(frozen=True)
class IndexQuote:
    index_code: str
    name: str
    last: float | None
    change: float | None
    change_pct: float | None
    quote_time: str
    source_id: str = SOURCE_ID
    quote_kind: str = QUOTE_KIND
    is_realtime: bool = False
    license_status: str = LICENSE_STATUS
    commercial_ok: bool = COMMERCIAL_OK


@dataclass(frozen=True)
class StockQuote:
    code: str
    name: str
    exchange: str
    board: str
    last: float | None
    change_pct: float | None
    prev_close: float | None
    amount: float | None
    market_cap: float | None
    quote_time: str
    source_id: str = SOURCE_ID
    quote_kind: str = QUOTE_KIND
    is_realtime: bool = False
    license_status: str = LICENSE_STATUS
    commercial_ok: bool = COMMERCIAL_OK


def _num(value: Any) -> float | None:
    if value is None or value == "-" or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _ts(value: Any) -> str:
    try:
        epoch = int(value)
        return datetime.fromtimestamp(epoch, tz=TZ).isoformat(timespec="seconds")
    except (TypeError, ValueError, OSError):
        return datetime.now(tz=TZ).isoformat(timespec="seconds")


def classify(exchange_market: int, code: str) -> tuple[str, str]:
    """Map Eastmoney market id + code to (exchange, board)."""
    if exchange_market == 1:
        board = "STAR" if code.startswith(("688", "689")) else "MAIN"
        return "SSE", board
    if code.startswith(("300", "301")):
        return "SZSE", "CHINEXT"
    if code.startswith(("920", "83", "87", "88")):
        return "BSE", "BSE"
    return "SZSE", "MAIN"


def parse_index_rows(rows: list[dict]) -> list[IndexQuote]:
    out: list[IndexQuote] = []
    for row in rows:
        code = str(row.get("f12") or "")
        if code not in INDEX_SECIDS:
            continue
        out.append(
            IndexQuote(
                index_code=code,
                name=str(row.get("f14") or ""),
                last=_num(row.get("f2")),
                change=_num(row.get("f4")),
                change_pct=_num(row.get("f3")),
                quote_time=_ts(row.get("f124")),
            )
        )
    return out


def parse_stock_rows(rows: list[dict]) -> list[StockQuote]:
    out: list[StockQuote] = []
    for row in rows:
        code = str(row.get("f12") or "").strip()
        if not code:
            continue
        last = _num(row.get("f2"))
        prev_close = _num(row.get("f18"))
        if last is None or last <= 0:
            continue  # suspended / no price: excluded from breadth, never faked
        exchange, board = classify(int(row.get("f13") or 0), code)
        out.append(
            StockQuote(
                code=code,
                name=str(row.get("f14") or ""),
                exchange=exchange,
                board=board,
                last=last,
                change_pct=_num(row.get("f3")),
                prev_close=prev_close,
                amount=_num(row.get("f6")),
                market_cap=_num(row.get("f20")),
                quote_time=_ts(row.get("f124")),
            )
        )
    return out


def _get_json(url: str, params: dict, attempts: int = 4) -> dict:
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            with httpx.Client(timeout=45.0, follow_redirects=True) as client:
                resp = client.get(url, params=params, headers=HEADERS)
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            time.sleep(1 + 2**attempt)
    raise RuntimeError(f"eastmoney request failed: {url}") from last_exc


def fetch_indices() -> list[IndexQuote]:
    params = {
        "fltt": "2",
        "invt": "2",
        "fields": "f2,f3,f4,f12,f13,f14,f124",
        "secids": ",".join(INDEX_SECIDS.values()),
    }
    payload = _get_json(INDEX_ULIST_URL, params)
    rows = (payload.get("data") or {}).get("diff") or []
    return parse_index_rows(rows)


def fetch_all_stocks(page_size: int = 100, page_delay: float = 0.15) -> list[StockQuote]:
    out: list[StockQuote] = []
    page = 1
    while True:
        params = {
            "pn": str(page),
            "pz": str(page_size),
            "po": "1",
            "np": "1",
            "fltt": "2",
            "invt": "2",
            "fid": "f3",
            "fs": MARKET_FS,
            "fields": "f2,f3,f6,f12,f13,f14,f18,f20,f124",
        }
        payload = _get_json(STOCK_CLIST_URL, params)
        data = payload.get("data") or {}
        rows = data.get("diff") or []
        if not rows:
            break
        out.extend(parse_stock_rows(rows))
        total = int(data.get("total") or len(out))
        if page * page_size >= total:
            break
        page += 1
        time.sleep(page_delay)
    return out
