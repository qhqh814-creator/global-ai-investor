"""Securities master data records and parsers (P1).

Sources:
- SSE: official query.sse.com.cn list (26 pages x 100; A shares: STOCK_TYPE 1/8)
- SZSE: official ShowReport catalog 1110 (A-share list, 146 pages x 20)
- BSE: Eastmoney clist fallback (official BSE list is behind a JS challenge);
       marked unlicensed_third_party in data_sources.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class SecurityRecord:
    code: str
    exchange: str
    board: str
    name_zh: str
    security_type: str = "STOCK"
    name_en: str | None = None
    listing_date: date | None = None
    status: str = "NORMAL"
    total_shares: int | None = None
    float_shares: int | None = None
    industry: str | None = None
    source_id: str = ""
    raw: dict = field(default_factory=dict, compare=False, repr=False)


def _parse_date(value: str | None) -> date | None:
    if not value or value in ("-", "--"):
        return None
    value = value.strip()
    if re.fullmatch(r"\d{8}", value):
        return date(int(value[0:4]), int(value[4:6]), int(value[6:8]))
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return date.fromisoformat(value)
    return None


def _strip_html(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"<[^>]+>", "", text).strip()


# ---------------------------------------------------------------- SSE
def parse_sse_rows(rows: list[dict]) -> list[SecurityRecord]:
    """Parse query.sse.com.cn A-share rows.

    STOCK_TYPE: 1 = 主板A股, 8 = 科创板; 2 = B股 (excluded).
    LIST_BOARD: 1 = 主板, 2 = 科创板.
    """
    out: list[SecurityRecord] = []
    for row in rows:
        stock_type = str(row.get("STOCK_TYPE") or "")
        code = (row.get("A_STOCK_CODE") or "").strip()
        if stock_type not in ("1", "8") or not code or code == "-":
            continue
        board = "STAR" if str(row.get("LIST_BOARD")) == "2" or code.startswith(("688", "689")) else "MAIN"
        out.append(
            SecurityRecord(
                code=code,
                exchange="SSE",
                board=board,
                name_zh=(row.get("SEC_NAME_CN") or row.get("COMPANY_ABBR") or "").strip(),
                name_en=(row.get("COMPANY_ABBR_EN") or "").strip() or None,
                listing_date=_parse_date(row.get("LIST_DATE")),
                industry=(row.get("CSRC_CODE_DESC") or "").strip() or None,
                source_id="sse_stock_list",
                raw=row,
            )
        )
    return out


# ---------------------------------------------------------------- SZSE
def parse_szse_rows(rows: list[dict]) -> list[SecurityRecord]:
    out: list[SecurityRecord] = []
    for row in rows:
        code = (row.get("agdm") or "").strip()
        if not code:
            continue
        board_name = (row.get("bk") or "").strip()
        board = "CHINEXT" if "创业" in board_name else "MAIN"
        total = _parse_yi_shares(row.get("agzgb"))
        float_shares = _parse_yi_shares(row.get("agltgb"))
        out.append(
            SecurityRecord(
                code=code,
                exchange="SZSE",
                board=board,
                name_zh=_strip_html(row.get("agjc")),
                listing_date=_parse_date(row.get("agssrq")),
                industry=(row.get("sshymc") or "").strip() or None,
                total_shares=total,
                float_shares=float_shares,
                source_id="szse_showreport",
                raw=row,
            )
        )
    return out


def _parse_yi_shares(value: str | None) -> int | None:
    """SZSE list reports share counts in 亿股 (e.g. 194.05)."""
    if not value or value in ("-", "--"):
        return None
    try:
        return int(round(float(value) * 100_000_000))
    except ValueError:
        return None


# ---------------------------------------------------------------- BSE
def parse_bse_rows(rows: list[dict]) -> list[SecurityRecord]:
    out: list[SecurityRecord] = []
    for row in rows:
        code = (row.get("f12") or "").strip()
        if not code:
            continue
        name = (row.get("f14") or "").strip()
        out.append(
            SecurityRecord(
                code=code,
                exchange="BSE",
                board="BSE",
                name_zh=name,
                industry=(row.get("f100") or "").strip() or None,
                source_id="eastmoney_bse_list",
                raw=row,
            )
        )
    return out
