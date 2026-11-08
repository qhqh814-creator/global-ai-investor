"""Securities master data fetchers (page-level network functions, P1).

Includes small retry helper because some exchange endpoints occasionally drop
connections through the local proxy.
"""

from __future__ import annotations

import time

import httpx

from ..securities.models import SecurityRecord, parse_bse_rows, parse_sse_rows, parse_szse_rows

UA = "GlobalAIInvestor/0.1 (personal research)"
SSE_LIST_URL = "https://query.sse.com.cn/sseQuery/commonQuery.do"
SZSE_LIST_URL = "https://www.szse.cn/api/report/ShowReport/data"
BSE_LIST_URL = "https://push2.eastmoney.com/api/qt/clist/get"


def _get(url: str, params: dict, headers: dict, attempts: int = 5) -> httpx.Response:
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            with httpx.Client(timeout=30.0, follow_redirects=True) as client:
                resp = client.get(url, params=params, headers=headers)
                resp.raise_for_status()
                return resp
        except Exception as exc:  # noqa: BLE001 - retry any transport/HTTP error
            last_exc = exc
            time.sleep(1 + 2**attempt)
    raise RuntimeError(f"GET failed after {attempts} attempts: {url}") from last_exc


def fetch_sse(page_size: int = 100, page_delay: float = 0.2) -> list[SecurityRecord]:
    records: list[SecurityRecord] = []
    headers = {"Referer": "https://www.sse.com.cn/", "User-Agent": UA}
    page = 1
    while True:
        params = {
            "sqlId": "COMMON_SSE_CP_GPJCTPZ_GPLB_GP_L",
            "isPagination": "true",
            "pageHelp.pageSize": str(page_size),
            "pageHelp.pageNo": str(page),
            "pageHelp.beginPage": str(page),
            "pageHelp.cacheSize": "1",
            "pageHelp.endPage": str(page),
        }
        payload = _get(SSE_LIST_URL, params, headers).json()
        rows = (payload.get("pageHelp") or {}).get("data") or []
        if not rows:
            break
        records.extend(parse_sse_rows(rows))
        total_pages = int((payload.get("pageHelp") or {}).get("pageCount") or page)
        if page >= total_pages:
            break
        page += 1
        time.sleep(page_delay)
    return records


def fetch_szse(page_delay: float = 0.2, max_pages: int | None = None) -> list[SecurityRecord]:
    records: list[SecurityRecord] = []
    headers = {"Referer": "https://www.szse.cn/", "User-Agent": UA}
    page = 1
    while True:
        params = {"SHOWTYPE": "JSON", "CATALOGID": "1110", "TABKEY": "tab1", "PAGENO": str(page)}
        payload = _get(SZSE_LIST_URL, params, headers).json()
        item = payload[0] if isinstance(payload, list) and payload else {}
        rows = item.get("data") or []
        meta = item.get("metadata") or {}
        if not rows:
            break
        records.extend(parse_szse_rows(rows))
        page_count = int(meta.get("pagecount") or page)
        if page >= page_count or (max_pages is not None and page >= max_pages):
            break
        page += 1
        time.sleep(page_delay)
    return records


def fetch_bse(page_delay: float = 0.2) -> list[SecurityRecord]:
    records: list[SecurityRecord] = []
    page = 1
    while True:
        params = {
            "pn": str(page),
            "pz": "100",
            "po": "1",
            "np": "1",
            "fltt": "2",
            "invt": "2",
            "fid": "f3",
            "fs": "m:0+t:81+s:2048",
            "fields": "f12,f14,f13,f100",
        }
        data = (_get(BSE_LIST_URL, params, {"User-Agent": UA}).json() or {}).get("data") or {}
        diff = data.get("diff") or []
        if not diff:
            break
        records.extend(parse_bse_rows(diff))
        total = int(data.get("total") or len(records))
        if len(records) >= total:
            break
        page += 1
        time.sleep(page_delay)
    return records
