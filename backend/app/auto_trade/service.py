"""Automatic paper execution for the daily AI pipeline.

Rules:
- 08:30 pipeline prepares plans; 09:35 auto-buy executes only READY BUY plans.
- Every 30 minutes in the trading session, auto-sell held stocks on:
  L3/L4 negative news, -8% stop loss, +8% take profit, or market crash
  (breadth up-ratio < 20%).
- Fills use the latest snapshot (not real-time); every action writes an alert.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone, timedelta

from ..analysis.recommendations import list_recommendations
from ..paper.service import place_order
from ..trading_plan.service import list_trade_plans, market_regime

TZ = timezone(timedelta(hours=8))
STOP_LOSS = -0.08
TAKE_PROFIT = 0.08


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def _quote(conn: sqlite3.Connection, code: str) -> dict | None:
    row = conn.execute("SELECT last, quote_time, source_id FROM stock_quotes WHERE code=?", (code,)).fetchone()
    return dict(row) if row else None


def _alert(conn: sqlite3.Connection, level: str, title: str, summary: str, code: str) -> None:
    with conn:
        conn.execute(
            "INSERT INTO alerts(level,title,summary,security_codes_json,evidence_json,source_type,source_id,status,triggered_at,updated_at) "
            "VALUES (?,?,?,?, '[]', 'auto_trade', NULL, 'OPEN', ?, ?)",
            (level, title[:200], summary, f'["{code}"]', now_iso(), now_iso()),
        )


def auto_buy_ready(conn: sqlite3.Connection) -> dict:
    """Buy READY plans not already held. Market-weak plans are WATCH and skipped."""
    placed = 0
    rejected = 0
    for plan in list_trade_plans(conn, limit=50):
        if plan["action"] != "BUY" or plan["status"] != "READY" or not plan["qty"]:
            continue
        code = plan["code"]
        held = conn.execute("SELECT 1 FROM sim_positions WHERE code=? LIMIT 1", (code,)).fetchone()
        if held:
            continue
        result = place_order(conn, code, "BUY", int(plan["qty"]), "MARKET")
        if result.get("status") == "FILLED":
            placed += 1
            _alert(conn, "L2", f"自动买入 {code}", f"按交易计划买入 {plan['qty']} 股；成交价 {result.get('price')}；止损 {plan['stop_loss']}，止盈 {plan['take_profit']}。", code)
        else:
            rejected += 1
            _alert(conn, "L2", f"自动买入失败 {code}", f"计划买入 {plan['qty']} 股被拒绝：{result.get('reason')}", code)
    return {"placed": placed, "rejected": rejected}


def risk_check(conn: sqlite3.Connection) -> dict:
    """Auto-sell held stocks on negative news / stop loss / take profit / market crash."""
    regime = market_regime(conn)
    crash = regime.get("up_ratio") is not None and regime["up_ratio"] < 0.20
    cutoff = (datetime.now(TZ) - timedelta(hours=36)).isoformat(timespec="seconds")
    sold = 0
    skipped = 0
    actions = []
    positions = conn.execute("SELECT code, qty, sellable_qty, avg_cost, buy_date FROM sim_positions").fetchall()
    for pos in positions:
        code = pos["code"]
        quote = _quote(conn, code)
        if not quote or not quote["last"]:
            skipped += 1
            continue
        quote_day = (quote.get("quote_time") or "")[:10]
        # T+1: compute sellable dynamically from buy_date, not a stale column
        sellable = int(pos["qty"]) if pos["buy_date"] and quote_day and pos["buy_date"] < quote_day else 0
        if sellable <= 0:
            skipped += 1
            continue
        reason = None
        level = "L3"
        if crash:
            reason = f"大盘急跌（上涨占比 {regime['up_ratio']:.0%}），自动卖出"
            level = "L4"
        else:
            negative = conn.execute(
                """
                SELECT a.materiality, a.summary FROM ai_analysis a
                JOIN news_stock_links l ON l.target_type=a.target_type AND l.target_id=a.target_id
                WHERE l.code=? AND a.sentiment='negative' AND a.materiality IN ('L3','L4') AND a.created_at>=?
                ORDER BY a.created_at DESC LIMIT 1
                """,
                (code, cutoff),
            ).fetchone()
            if negative:
                reason = f"持仓出现 {negative['materiality']} 负向消息：{negative['summary'][:120]}"
            elif pos["avg_cost"]:
                pnl = (float(quote["last"]) - float(pos["avg_cost"])) / float(pos["avg_cost"])
                if pnl <= STOP_LOSS:
                    reason = f"浮亏 {pnl*100:.2f}% 触发 -8% 止损"
                elif pnl >= TAKE_PROFIT:
                    reason = f"浮盈 {pnl*100:.2f}% 触发 +8% 止盈"
                    level = "L2"
        if not reason:
            continue
        result = place_order(conn, code, "SELL", int(sellable), "MARKET")
        if result.get("status") == "FILLED":
            sold += 1
            actions.append({"code": code, "qty": sellable, "reason": reason})
            _alert(conn, level, f"自动卖出 {code}", f"{reason}；卖出 {sellable} 股，成交价 {result.get('price')}。", code)
        else:
            skipped += 1
            _alert(conn, "L3", f"自动卖出失败 {code}", f"{reason}；卖出被拒绝：{result.get('reason')}", code)
    return {"sold": sold, "skipped": skipped, "actions": actions, "crash": crash}
