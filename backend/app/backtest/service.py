"""Historical backtest engine (P5).

Rule-version aware: fees/limits/lot sizes are resolved per trade date from the
rule library. Daily bars only; documented simplifications:
- entry uses previous trading day's change_pct, executed at today's open;
- cannot buy at limit-up open, cannot sell at limit-down open (retry next day);
- no intraday fills, no slippage unless configured;
- forced mark-to-market at last close for open positions.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone, timedelta

from ..klines.service import load_bars
from ..rules import get_library
from ..rules.fees import calc_fees, limit_down_price, limit_up_price

TZ = timezone(timedelta(hours=8))
COMMISSION_RATE = 0.0003


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def _single_rule(conn: sqlite3.Connection, code: str):
    sec = conn.execute("SELECT exchange, board, name_zh FROM securities WHERE code = ?", (code,)).fetchone()
    if sec:
        return sec["exchange"], sec["board"], sec["name_zh"] or ""
    q = conn.execute("SELECT exchange, board, name FROM stock_quotes WHERE code = ?", (code,)).fetchone()
    if q:
        return q["exchange"], q["board"], q["name"] or ""
    return None


def run_backtest(
    conn: sqlite3.Connection,
    codes: list[str],
    start_date: str,
    end_date: str,
    initial_cash: float = 1_000_000.0,
    entry_pct: float = 5.0,
    hold_days: int = 3,
    max_positions: int = 5,
) -> dict:
    lib = get_library()
    params = {
        "entry_pct": entry_pct,
        "hold_days": hold_days,
        "max_positions": max_positions,
        "commission_rate": COMMISSION_RATE,
        "note": "daily bars; entry on next open; limit-up buy / limit-down sell blocked",
    }
    series: dict[str, list[dict]] = {}
    for code in codes:
        bars = load_bars(conn, code, start_date, end_date)
        if len(bars) >= 3:
            series[code] = bars
    ts = now_iso()
    with conn:
        cur = conn.execute(
            "INSERT INTO backtests(name, params_json, codes_json, start_date, end_date, initial_cash, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'RUNNING', ?)",
            ("momentum", json.dumps(params, ensure_ascii=False), json.dumps(codes), start_date, end_date, initial_cash, ts),
        )
        backtest_id = int(cur.lastrowid)

    if not series:
        with conn:
            conn.execute("UPDATE backtests SET status='FAILED' WHERE id=?", (backtest_id,))
        return {"backtest_id": backtest_id, "status": "FAILED", "reason": "no kline data for requested codes/range"}

    dates = sorted({b["trade_date"] for bars in series.values() for b in bars})
    bars_by_date: dict[str, dict[str, dict]] = {d: {} for d in dates}
    prev_bar: dict[str, dict | None] = {code: None for code in series}
    index_by_date: dict[str, dict[str, int]] = {code: {b["trade_date"]: i for i, b in enumerate(bars)} for code, bars in series.items()}
    for code, bars in series.items():
        for b in bars:
            bars_by_date.setdefault(b["trade_date"], {})[code] = b

    cash = float(initial_cash)
    positions: dict[str, dict] = {}  # code -> {qty, cost, buy_date, buy_price}
    trades: list[dict] = []
    equity_curve: list[dict] = []
    closed_pnls: list[float] = []

    for day in dates:
        # 1) sells first
        for code in list(positions.keys()):
            pos = positions[code]
            bar = bars_by_date.get(day, {}).get(code)
            if not bar:
                continue
            idx = index_by_date[code][day]
            if idx <= 0:
                continue
            held = idx - index_by_date[code][pos["buy_date"]] if pos["buy_date"] in index_by_date[code] else 0
            if held < hold_days:
                continue
            prev_close = series[code][idx - 1]["close"]
            rules = None
            down = 0.0
            if prev_close:
                try:
                    version, rules = lib.select(pos["exchange"], pos["board"], pos["risk"], "SEASONED", datetime.fromisoformat(day).date())  # type: ignore[arg-type]
                    down = limit_down_price(prev_close, rules.price_limit.down_pct or 0) if rules.price_limit.type == "PCT" else 0.0
                except LookupError:
                    rules = None
            if rules is None:
                continue
            if down and bar["open"] <= down:
                continue  # cannot sell at limit-down open; retry next day
            exec_price = bar["open"]
            amount = exec_price * pos["qty"]
            fee = calc_fees(amount, "SELL", rules.fees, COMMISSION_RATE)  # type: ignore[possibly-undefined]
            cash += amount - fee.total
            pnl = (exec_price - pos["cost"]) * pos["qty"] - fee.total
            closed_pnls.append(pnl)
            trades.append({
                "code": code, "side": "SELL", "trade_date": day, "price": exec_price,
                "qty": pos["qty"], "fee_total": fee.total, "fee_json": fee.as_dict(),
                "rule_version_id": version.version_code, "note": f"held {held} days",
            })
            del positions[code]

        # 2) buys
        for code, bars in series.items():
            if code in positions or len(positions) >= max_positions:
                continue
            bar = bars_by_date.get(day, {}).get(code)
            if not bar:
                continue
            idx = index_by_date[code][day]
            if idx <= 0:
                continue
            yest = bars[idx - 1]
            if yest["change_pct"] < entry_pct:
                continue
            sec = _single_rule(conn, code)
            if not sec:
                continue
            exchange, board, name = sec
            risk = "ST" if "ST" in name.upper() else "NORMAL"
            try:
                version, rules = lib.select(exchange, board, risk, "SEASONED", datetime.fromisoformat(day).date())  # type: ignore[arg-type]
            except LookupError:
                continue
            if rules.price_limit.type == "PCT" and yest["close"]:
                up = limit_up_price(yest["close"], rules.price_limit.up_pct or 0)
                if bar["open"] >= up:
                    continue  # cannot buy at limit-up open
            budget = initial_cash / max_positions
            step = rules.order.step if rules.order.multiple_required else rules.order.step
            lot = int(budget // (bar["open"] * step)) * step
            if lot < rules.order.min_qty:
                continue
            amount = bar["open"] * lot
            fee = calc_fees(amount, "BUY", rules.fees, COMMISSION_RATE)
            if amount + fee.total > cash:
                lot = int((cash / (bar["open"] * step)) // 1) * step
                if lot < rules.order.min_qty:
                    continue
                amount = bar["open"] * lot
                fee = calc_fees(amount, "BUY", rules.fees, COMMISSION_RATE)
            cash -= amount + fee.total
            positions[code] = {"qty": lot, "cost": bar["open"], "buy_date": day, "exchange": exchange,
                               "board": board, "risk": risk}
            trades.append({
                "code": code, "side": "BUY", "trade_date": day, "price": bar["open"],
                "qty": lot, "fee_total": fee.total, "fee_json": fee.as_dict(),
                "rule_version_id": version.version_code, "note": f"entry pct {yest['change_pct']:.2f}",
            })

        # 3) mark to market
        market_value = 0.0
        for code, pos in positions.items():
            bar = bars_by_date.get(day, {}).get(code)
            if bar:
                market_value += bar["close"] * pos["qty"]
        equity_curve.append({"date": day, "equity": round(cash + market_value, 2)})

    final_equity = equity_curve[-1]["equity"] if equity_curve else initial_cash
    peak = initial_cash
    max_dd = 0.0
    for point in equity_curve:
        peak = max(peak, point["equity"])
        max_dd = max(max_dd, (peak - point["equity"]) / peak if peak else 0)
    wins = [p for p in closed_pnls if p > 0]
    losses = [p for p in closed_pnls if p <= 0]
    profit_factor = (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else (float("inf") if wins else 0.0)
    total_return = (final_equity - initial_cash) / initial_cash
    days = max(1, len(equity_curve))
    annual_return = (1 + total_return) ** (252 / days) - 1 if total_return > -1 else -1.0
    metrics = {
        "total_return": round(total_return, 6),
        "annual_return": round(annual_return, 6),
        "max_drawdown": round(max_dd, 6),
        "win_rate": round(len(wins) / len(closed_pnls), 6) if closed_pnls else 0.0,
        "profit_factor": round(profit_factor, 6) if profit_factor != float("inf") else 999.0,
        "trades_count": len(trades),
        "final_equity": round(final_equity, 2),
        "equity_curve": equity_curve[-200:],
    }
    with conn:
        conn.executemany(
            "INSERT INTO backtest_trades(backtest_id, code, side, trade_date, price, qty, fee_total, fee_json, rule_version_id, note) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(backtest_id, t["code"], t["side"], t["trade_date"], t["price"], t["qty"], t["fee_total"],
              json.dumps(t["fee_json"], ensure_ascii=False), t["rule_version_id"], t["note"]) for t in trades],
        )
        conn.execute(
            "INSERT OR REPLACE INTO backtest_metrics(backtest_id, total_return, annual_return, max_drawdown, win_rate, "
            "profit_factor, trades_count, final_equity, equity_curve_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (backtest_id, metrics["total_return"], metrics["annual_return"], metrics["max_drawdown"],
             metrics["win_rate"], metrics["profit_factor"], metrics["trades_count"], metrics["final_equity"],
             json.dumps(metrics["equity_curve"])),
        )
        conn.execute("UPDATE backtests SET status='DONE' WHERE id=?", (backtest_id,))
    return {"backtest_id": backtest_id, "status": "DONE", "metrics": metrics, "trades": trades}


def get_backtest(conn: sqlite3.Connection, backtest_id: int) -> dict | None:
    run = conn.execute("SELECT * FROM backtests WHERE id = ?", (backtest_id,)).fetchone()
    if not run:
        return None
    metrics = conn.execute("SELECT * FROM backtest_metrics WHERE backtest_id = ?", (backtest_id,)).fetchone()
    trades = conn.execute("SELECT * FROM backtest_trades WHERE backtest_id = ? ORDER BY trade_date, id", (backtest_id,)).fetchall()
    return {
        "run": {k: run[k] for k in run.keys()},
        "metrics": {k: metrics[k] for k in metrics.keys()} if metrics else None,
        "trades": [dict(t) for t in trades],
    }



