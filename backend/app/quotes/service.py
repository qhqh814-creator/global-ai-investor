"""Dashboard quote aggregation (P2).

Real snapshots only: if a source fails, cards report unavailable with a reason.
Breadth / limit counts are computed from the effective rule library (never a
hard-coded 10%).
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone

from ..datasources.quote_eastmoney import (
    COMMERCIAL_OK,
    LICENSE_STATUS,
    QUOTE_KIND,
    SOURCE_ID,
    IndexQuote,
    StockQuote,
    fetch_all_stocks,
    fetch_indices,
)
from ..rules import get_library
from ..rules.fees import limit_down_price, limit_up_price

TZ = timezone(timedelta(hours=8))
DATA_KEYS = [
    "dashboard.sse_index",
    "dashboard.szse_index",
    "dashboard.chinext_index",
    "dashboard.star50",
    "dashboard.bse50",
    "dashboard.market_breadth",
    "dashboard.limit_counts",
    "dashboard.turnover",
]


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def provenance(quote_time: str | None, fetched_at: str) -> dict:
    return {
        "sourceIds": [SOURCE_ID],
        "quoteTime": quote_time,
        "fetchedAt": fetched_at,
        "isRealtime": False,
        "kind": QUOTE_KIND,
        "licenseStatus": LICENSE_STATUS,
        "commercialOk": COMMERCIAL_OK,
    }


def _is_new_listing(conn: sqlite3.Connection, code: str, trade_date: date) -> bool:
    row = conn.execute("SELECT listing_date FROM securities WHERE code = ?", (code,)).fetchone()
    if not row or not row["listing_date"]:
        return False
    try:
        listed = date.fromisoformat(row["listing_date"])
    except ValueError:
        return False
    if listed > trade_date:
        return False
    # 10 calendar days is a conservative proxy for IPO_DAY1..5; special rules
    # exclude these from limit-count statistics (documented in breadth.note).
    return (trade_date - listed) <= timedelta(days=10)


def compute_breadth(conn: sqlite3.Connection, stocks: list[StockQuote], trade_date: date) -> dict:
    lib = get_library()
    up = down = flat = limit_up = limit_down = 0
    total_amount = 0.0
    excluded_new = 0

    for s in stocks:
        pct = s.change_pct
        if pct is None:
            continue
        if pct > 0:
            up += 1
        elif pct < 0:
            down += 1
        else:
            flat += 1
        if s.amount:
            total_amount += s.amount

        if _is_new_listing(conn, s.code, trade_date):
            excluded_new += 1
            continue
        risk = "ST" if "ST" in s.name.upper() else "NORMAL"
        try:
            _, rules = lib.select(s.exchange, s.board, risk, "SEASONED", trade_date)  # type: ignore[arg-type]
        except LookupError:
            continue
        if rules.price_limit.type != "PCT" or not s.prev_close:
            continue
        up_price = limit_up_price(s.prev_close, rules.price_limit.up_pct or 0)
        down_price = limit_down_price(s.prev_close, rules.price_limit.down_pct or 0)
        if abs(s.last - up_price) < 0.005:
            limit_up += 1
        elif abs(s.last - down_price) < 0.005:
            limit_down += 1

    note = "按现行规则库计算；剔除停牌/无价证券"
    if excluded_new:
        note += f"；剔除近10日新股{excluded_new}只（特殊涨跌幅规则）"
    return {
        "trade_date": trade_date.isoformat(),
        "up_count": up,
        "down_count": down,
        "flat_count": flat,
        "limit_up_count": limit_up,
        "limit_down_count": limit_down,
        "total_amount": total_amount,
        "note": note,
    }


def upsert_availability(conn: sqlite3.Connection, key: str, status: str, reason: str | None, detail: str | None) -> None:
    ts = now_iso()
    with conn:
        conn.execute(
            """
            INSERT INTO data_availability(data_key, status, reason_code, detail, last_success_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(data_key) DO UPDATE SET
                status=excluded.status,
                reason_code=excluded.reason_code,
                detail=excluded.detail,
                last_success_at=CASE WHEN excluded.status='AVAILABLE' THEN excluded.last_success_at ELSE data_availability.last_success_at END,
                updated_at=excluded.updated_at
            """,
            (key, status, reason, detail, ts if status == "AVAILABLE" else None, ts),
        )


def sync_quotes(
    conn: sqlite3.Connection,
    fetch_indices_fn=fetch_indices,
    fetch_stocks_fn=fetch_all_stocks,
) -> dict:
    fetched_at = now_iso()
    errors: list[str] = []
    indices: list[IndexQuote] = []
    stocks: list[StockQuote] = []
    try:
        indices = fetch_indices_fn()
    except Exception as exc:  # noqa: BLE001
        errors.append(f"indices: {exc}")
    try:
        stocks = fetch_stocks_fn()
    except Exception as exc:  # noqa: BLE001
        errors.append(f"stocks: {exc}")

    if indices:
        with conn:
            conn.executemany(
                """
                INSERT INTO index_quotes(index_code, name, quote_time, last, change, change_pct,
                    source_id, quote_kind, is_realtime, license_status, commercial_ok, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, 0, ?)
                """,
                [
                    (q.index_code, q.name, q.quote_time, q.last, q.change, q.change_pct,
                     q.source_id, q.quote_kind, q.license_status, fetched_at)
                    for q in indices
                ],
            )
        for q in indices:
            key = {
                "000001": "dashboard.sse_index",
                "399001": "dashboard.szse_index",
                "399006": "dashboard.chinext_index",
                "000688": "dashboard.star50",
                "899050": "dashboard.bse50",
            }[q.index_code]
            upsert_availability(conn, key, "AVAILABLE", None, None)

    breadth: dict | None = None
    if stocks:
        # Trade date comes from the data itself (quote_time), not the fetch day;
        # otherwise a weekend/holiday sync would be misdated.
        try:
            trade_date = date.fromisoformat(max(s.quote_time for s in stocks)[:10])
        except (ValueError, TypeError):
            trade_date = date.today()
        quotes_time = max((s.quote_time for s in stocks), default=None)
        breadth = compute_breadth(conn, stocks, trade_date)
        with conn:
            conn.executemany(
                """
                INSERT INTO stock_quotes(code, name, exchange, board, last, change_pct, prev_close,
                    amount, market_cap, quote_time, source_id, quote_kind, is_realtime,
                    license_status, commercial_ok, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, 0, ?)
                ON CONFLICT(code) DO UPDATE SET
                    name=excluded.name, exchange=excluded.exchange, board=excluded.board,
                    last=excluded.last, change_pct=excluded.change_pct, prev_close=excluded.prev_close,
                    amount=excluded.amount, market_cap=excluded.market_cap, quote_time=excluded.quote_time,
                    source_id=excluded.source_id, fetched_at=excluded.fetched_at
                """,
                [
                    (s.code, s.name, s.exchange, s.board, s.last, s.change_pct, s.prev_close,
                     s.amount, s.market_cap, s.quote_time, s.source_id, s.quote_kind, s.license_status,
                     fetched_at)
                    for s in stocks
                ],
            )
            conn.execute(
                """
                INSERT INTO market_breadth(trade_date, quote_time, up_count, down_count, flat_count,
                    limit_up_count, limit_down_count, total_amount, source_id, is_realtime,
                    license_status, commercial_ok, note, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, 0, ?, ?)
                """,
                (breadth["trade_date"], quotes_time, breadth["up_count"], breadth["down_count"],
                 breadth["flat_count"], breadth["limit_up_count"], breadth["limit_down_count"],
                 breadth["total_amount"], SOURCE_ID, LICENSE_STATUS, breadth["note"], fetched_at),
            )
        for key in ("dashboard.market_breadth", "dashboard.limit_counts", "dashboard.turnover"):
            upsert_availability(conn, key, "AVAILABLE", None, None)

    if errors:
        for key in DATA_KEYS:
            if key in ("dashboard.market_breadth", "dashboard.limit_counts", "dashboard.turnover") and breadth:
                continue
            row = conn.execute("SELECT status FROM data_availability WHERE data_key = ?", (key,)).fetchone()
            if not row or row["status"] != "AVAILABLE":
                upsert_availability(conn, key, "UNAVAILABLE", "upstream_error", "; ".join(errors))

    return {
        "indices": len(indices),
        "stocks": len(stocks),
        "breadth": breadth,
        "errors": errors,
        "fetched_at": fetched_at,
    }


def _latest_index(conn: sqlite3.Connection, code: str) -> dict | None:
    row = conn.execute(
        "SELECT index_code, name, quote_time, last, change, change_pct, source_id, license_status, fetched_at "
        "FROM index_quotes WHERE index_code = ? ORDER BY quote_time DESC, id DESC LIMIT 1",
        (code,),
    ).fetchone()
    return dict(row) if row else None


def get_dashboard(conn: sqlite3.Connection) -> dict:
    cards: list[dict] = []
    fetched_at = now_iso()
    b_row = conn.execute(
        "SELECT * FROM market_breadth ORDER BY fetched_at DESC, id DESC LIMIT 1"
    ).fetchone()
    breadth = dict(b_row) if b_row else None

    def index_card(key: str, code: str) -> dict:
        q = _latest_index(conn, code)
        if not q or q["last"] is None:
            return {"key": key, "value": None, "status": "unavailable",
                    "reason": "data_not_synced", "provenance": None}
        pct = q["change_pct"]
        value = f"{q['last']:,.2f} ({pct:+.2f}%)" if pct is not None else f"{q['last']:,.2f}"
        return {
            "key": key,
            "value": value,
            "status": "available",
            "reason": None,
            "provenance": provenance(q["quote_time"], q["fetched_at"]),
        }

    for key, code in [
        ("dashboard.sse_index", "000001"),
        ("dashboard.szse_index", "399001"),
        ("dashboard.chinext_index", "399006"),
        ("dashboard.star50", "000688"),
        ("dashboard.bse50", "899050"),
    ]:
        cards.append(index_card(key, code))

    quote_count = conn.execute("SELECT COUNT(*) AS n FROM stock_quotes").fetchone()["n"]
    if quote_count:
        latest_stock = conn.execute(
            "SELECT quote_time, fetched_at FROM stock_quotes ORDER BY fetched_at DESC LIMIT 1"
        ).fetchone()
        cards.append({
            "key": "dashboard.market_overview",
            "value": f"沪深北 A股快照 {int(quote_count):,} 只",
            "status": "available",
            "reason": None,
            "provenance": provenance(latest_stock["quote_time"], latest_stock["fetched_at"]),
        })
    else:
        cards.append({"key": "dashboard.market_overview", "value": None,
                      "status": "unavailable", "reason": "data_not_synced", "provenance": None})

    if breadth:
        prov = provenance(breadth["quote_time"], breadth["fetched_at"])
        cards.append({
            "key": "dashboard.market_breadth",
            "value": f"上涨 {breadth['up_count']} / 下跌 {breadth['down_count']} / 平盘 {breadth['flat_count']}",
            "status": "available", "reason": None, "provenance": prov,
        })
        cards.append({
            "key": "dashboard.limit_counts",
            "value": f"涨停 {breadth['limit_up_count']} / 跌停 {breadth['limit_down_count']}",
            "status": "available", "reason": None, "provenance": prov,
        })
        cards.append({
            "key": "dashboard.turnover",
            "value": f"成交额 {breadth['total_amount'] / 1e8:,.2f} 亿元",
            "status": "available", "reason": None, "provenance": prov,
        })
    else:
        for key in ("dashboard.market_breadth", "dashboard.limit_counts", "dashboard.turnover"):
            cards.append({"key": key, "value": None, "status": "unavailable",
                          "reason": "data_not_synced", "provenance": None})

    for key, reason in [
        ("dashboard.good_news", "p3_not_connected"),
        ("dashboard.risk_alerts", "p3_not_connected"),
        ("dashboard.ai_opportunities", "p3_not_connected"),
        ("dashboard.watchlist", "p4_not_connected"),
        ("dashboard.signals", "p4_not_connected"),
        ("dashboard.paper_account", "p5_not_connected"),
    ]:
        cards.append({"key": key, "value": None, "status": "unavailable", "reason": reason, "provenance": None})

    if breadth:
        cards[6]["value"] += f"（{breadth['note']}）"
    return {"cards": cards, "time": fetched_at}
