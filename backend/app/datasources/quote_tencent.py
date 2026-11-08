"""Tencent quote fallback (P2).

Verified 2026-11-08: https://qt.gtimg.cn/q=sh000001,... returns GBK text.
Unlicensed third-party snapshot; used only as failover for indices.
"""

from __future__ import annotations

import httpx

from .quote_eastmoney import IndexQuote

SOURCE_ID = "tencent_quote"
LICENSE_STATUS = "unlicensed_third_party"
BASE = "https://qt.gtimg.cn/q="

TENCENT_CODES: dict[str, str] = {
    "sh000001": "000001",
    "sz399001": "399001",
    "sz399006": "399006",
    "sh000688": "000688",
    "bj899050": "899050",
}


def _num(value: str) -> float | None:
    try:
        if value in ("", "-"):
            return None
        return float(value)
    except ValueError:
        return None


def parse_tencent(text: str) -> list[IndexQuote]:
    out: list[IndexQuote] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        key, _, payload = line.partition("=")
        code = key.replace("v_", "").strip()
        if code not in TENCENT_CODES:
            continue
        body = payload.strip().strip('";')
        parts = body.split("~")
        if len(parts) < 33:
            continue
        ts = parts[30].strip()
        quote_time = f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]}T{ts[8:10]}:{ts[10:12]}:{ts[12:14]}+08:00" if len(ts) >= 14 else ""
        out.append(
            IndexQuote(
                index_code=TENCENT_CODES[code],
                name=parts[1].strip(),
                last=_num(parts[3]),
                change=_num(parts[31]),
                change_pct=_num(parts[32]),
                quote_time=quote_time,
                source_id=SOURCE_ID,
                license_status=LICENSE_STATUS,
            )
        )
    return out


def fetch_index_quotes() -> list[IndexQuote]:
    url = BASE + ",".join(TENCENT_CODES.keys())
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        resp = client.get(url, headers={"User-Agent": "GlobalAIInvestor/0.1 (personal research)"})
        resp.raise_for_status()
        text = resp.content.decode("gbk", errors="ignore")
    return parse_tencent(text)
