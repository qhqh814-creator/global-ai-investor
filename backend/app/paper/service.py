"""Local paper-trading account (P5).

Uses the same rule engine as the real backtest: quantity/tick/price-limit/
T+1/ST-cap checks all come from the effective rule set. Fills are simplified
(latest snapshot price for market orders; crossing limit orders fill at last).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone, timedelta

from ..rules import get_library
from ..rules.fees import calc_fees
from ..rules.validator import OrderRequest, validate_order

TZ = timezone(timedelta(hours=8))
DEFAULT_ACCOUNT = "默认模拟账户"
DEFAULT_CASH = 1_000_000.0
COMMISSION_RATE = 0.0003


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def ensure_account(conn: sqlite3.Connection, initial_cash: float = DEFAULT_CASH) -> int:
    with conn:
        conn.execute(
            "INSERT INTO sim_accounts(name, initial_cash, cash, created_at) VALUES (?, ?, ?, ?) ON CONFLICT(name) DO NOTHING",
            (DEFAULT_ACCOUNT, initial_cash, initial_cash, now_iso()),
        )
    row = conn.execute("SELECT id FROM sim_accounts WHERE name = ?", (DEFAULT_ACCOUNT,)).fetchone()
    return int(row["id"]) if row else 0


def _account(conn: sqlite3.Connection, account_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM sim_accounts WHERE id = ?", (account_id,)).fetchone()
    if not row:
        raise ValueError("account not found")
    return row


def _security(conn: sqlite3.Connection, code: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM securities WHERE code = ?", (code,)).fetchone()


def _quote(conn: sqlite3.Connection, code: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM stock_quotes WHERE code = ?", (code,)).fetchone()


def _position(conn: sqlite3.Connection, account_id: int, code: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM sim_positions WHERE account_id = ? AND code = ?", (account_id, code)).fetchone()


def place_order(
    conn: sqlite3.Connection,
    code: str,
    side: str,
    qty: int,
    order_type: str = "MARKET",
    price: float | None = None,
) -> dict:
    account_id = ensure_account(conn)
    acc = _account(conn, account_id)
    sec = _security(conn, code)
    quote = _quote(conn, code)
    if not sec:
        return {"status": "REJECTED", "reason": "SECURITY_NOT_FOUND"}
    if not quote or not quote["last"]:
        return {"status": "REJECTED", "reason": "QUOTE_UNAVAILABLE"}

    trade_date = (quote["quote_time"] or "")[:10]
    name = sec["name_zh"] or ""
    risk = "ST" if "ST" in name.upper() else "NORMAL"
    try:
        version, rules = get_library().select(sec["exchange"], sec["board"], risk, "SEASONED",
                                              datetime.fromisoformat(trade_date).date())  # type: ignore[arg-type]
    except LookupError as exc:
        return {"status": "REJECTED", "reason": f"RULE_NOT_FOUND: {exc}"}

    pos = _position(conn, account_id, code)
    position_qty = pos["qty"] if pos else 0
    sellable = 0
    if pos and pos["buy_date"] != trade_date:
        sellable = pos["qty"]
    elif pos:
        sellable = 0  # T+1

    order = OrderRequest(
        exchange=sec["exchange"],
        board=sec["board"],
        security_code=code,
        side=side.upper(),
        qty=qty,
        order_type=order_type.upper(),
        price=price,
        session="CONTINUOUS",
        prev_close=quote["prev_close"],
        position_qty=position_qty,
        position_sellable=sellable,
        risk_warning_bought_today=0,
        best_bid=quote["last"],
        best_ask=quote["last"],
        last_price=quote["last"],
    )
    validation = validate_order(order, version, rules)
    if not validation.ok:
        return {"status": "REJECTED", "reason": validation.errors}

    last = float(quote["last"])
    if order_type.upper() == "MARKET":
        fill_price = last
    else:
        if price is None:
            return {"status": "REJECTED", "reason": ["PRICE_REQUIRED"]}
        fill_price = last
        if side.upper() == "BUY" and price < last:
            return {"status": "REJECTED", "reason": ["LIMIT_NOT_MARKETABLE"]}
        if side.upper() == "SELL" and price > last:
            return {"status": "REJECTED", "reason": ["LIMIT_NOT_MARKETABLE"]}

    amount = fill_price * qty
    fee = calc_fees(amount, side.upper(), rules.fees, COMMISSION_RATE)  # type: ignore[arg-type]
    ts = now_iso()
    with conn:
        cur = conn.execute(
            "INSERT INTO sim_orders(account_id, code, side, order_type, price, qty, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'FILLED', ?)",
            (account_id, code, side.upper(), order_type.upper(), price, qty, ts),
        )
        order_id = int(cur.lastrowid)

    if side.upper() == "BUY":
        total_cost = amount + fee.total
        if total_cost > acc["cash"]:
            with conn:
                conn.execute("UPDATE sim_orders SET status='REJECTED', reject_reason='INSUFFICIENT_CASH' WHERE id=?", (order_id,))
            return {"status": "REJECTED", "reason": ["INSUFFICIENT_CASH"]}
        new_qty = position_qty + qty
        if pos:
            new_cost = (pos["avg_cost"] * pos["qty"] + total_cost) / new_qty
            with conn:
                conn.execute(
                    "UPDATE sim_positions SET qty=?, sellable_qty=0, avg_cost=?, buy_date=?, updated_at=? "
                    "WHERE account_id=? AND code=?",
                    (new_qty, new_cost, trade_date, ts, account_id, code),
                )
        else:
            with conn:
                conn.execute(
                    "INSERT INTO sim_positions(account_id, code, qty, sellable_qty, avg_cost, buy_date, updated_at) "
                    "VALUES (?, ?, ?, 0, ?, ?, ?)",
                    (account_id, code, new_qty, total_cost / new_qty, trade_date, ts),
                )
        with conn:
            conn.execute("UPDATE sim_accounts SET cash = cash - ? WHERE id=?", (total_cost, account_id))
            conn.execute(
                "INSERT INTO sim_trades(order_id, code, side, trade_date, price, qty, fee_total, fee_json, rule_version_id, created_at) "
                "VALUES (?, ?, 'BUY', ?, ?, ?, ?, ?, ?, ?)",
                (order_id, code, trade_date, fill_price, qty, fee.total, json.dumps(fee.as_dict()), version.version_code, ts),
            )
    else:
        proceeds = amount - fee.total
        with conn:
            conn.execute("UPDATE sim_accounts SET cash = cash + ? WHERE id=?", (proceeds, account_id))
            conn.execute(
                "INSERT INTO sim_trades(order_id, code, side, trade_date, price, qty, fee_total, fee_json, rule_version_id, created_at) "
                "VALUES (?, ?, 'SELL', ?, ?, ?, ?, ?, ?, ?)",
                (order_id, code, trade_date, fill_price, qty, fee.total, json.dumps(fee.as_dict()), version.version_code, ts),
            )
            remaining = position_qty - qty
            if remaining <= 0:
                conn.execute("DELETE FROM sim_positions WHERE account_id=? AND code=?", (account_id, code))
            else:
                conn.execute(
                    "UPDATE sim_positions SET qty=?, sellable_qty=?, updated_at=? WHERE account_id=? AND code=?",
                    (remaining, remaining, ts, account_id, code),
                )
    return {
        "status": "FILLED",
        "order_id": order_id,
        "code": code,
        "side": side.upper(),
        "price": fill_price,
        "qty": qty,
        "fee_total": fee.total,
        "rule_version_id": version.version_code,
        "trade_date": trade_date,
    }


def get_account(conn: sqlite3.Connection) -> dict:
    account_id = ensure_account(conn)
    acc = _account(conn, account_id)
    rows = conn.execute(
        """
        SELECT p.code, p.qty, p.sellable_qty, p.avg_cost, p.buy_date, s.name_zh, q.last, q.quote_time
        FROM sim_positions p
        LEFT JOIN securities s ON s.code = p.code
        LEFT JOIN stock_quotes q ON q.code = p.code
        WHERE p.account_id = ?
        """,
        (account_id,),
    ).fetchall()
    positions = []
    market_value = 0.0
    for r in rows:
        last = r["last"] or 0.0
        market_value += last * r["qty"]
        positions.append({
            "code": r["code"], "name": r["name_zh"], "qty": r["qty"],
            "sellable_qty": r["sellable_qty"], "avg_cost": round(r["avg_cost"], 4),
            "last": r["last"], "quote_time": r["quote_time"],
            "pnl": round((last - r["avg_cost"]) * r["qty"], 2) if last else 0.0,
        })
    total_asset = round(acc["cash"] + market_value, 2)
    trade_date = datetime.now(TZ).date().isoformat()
    if positions and positions[0]["quote_time"]:
        trade_date = positions[0]["quote_time"][:10]
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO sim_nav(account_id, trade_date, total_asset, cash, market_value, pnl, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (account_id, trade_date, total_asset, round(acc["cash"], 2), round(market_value, 2),
             round(total_asset - acc["initial_cash"], 2), now_iso()),
        )
    return {
        "account": {"id": account_id, "name": acc["name"], "initial_cash": acc["initial_cash"], "cash": round(acc["cash"], 2)},
        "positions": positions,
        "total_asset": total_asset,
        "market_value": round(market_value, 2),
        "pnl": round(total_asset - acc["initial_cash"], 2),
    }


def list_orders(conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
    rows = conn.execute(
        "SELECT id, account_id, code, side, order_type, price, qty, status, reject_reason, created_at "
        "FROM sim_orders ORDER BY id DESC LIMIT ?",
        (max(1, min(limit, 500)),),
    ).fetchall()
    return [dict(r) for r in rows]


def list_trades(conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
    rows = conn.execute(
        "SELECT id, order_id, code, side, trade_date, price, qty, fee_total, rule_version_id, created_at "
        "FROM sim_trades ORDER BY id DESC LIMIT ?",
        (max(1, min(limit, 500)),),
    ).fetchall()
    return [dict(r) for r in rows]


def reset_account(conn: sqlite3.Connection) -> dict:
    account_id = ensure_account(conn)
    with conn:
        conn.execute("DELETE FROM sim_positions WHERE account_id=?", (account_id,))
        conn.execute("DELETE FROM sim_nav WHERE account_id=?", (account_id,))
        conn.execute("DELETE FROM sim_trades WHERE order_id IN (SELECT id FROM sim_orders WHERE account_id=?)", (account_id,))
        conn.execute("DELETE FROM sim_orders WHERE account_id=?", (account_id,))
        conn.execute("UPDATE sim_accounts SET cash = initial_cash WHERE id=?", (account_id,))
    return {"ok": True, "account_id": account_id}

