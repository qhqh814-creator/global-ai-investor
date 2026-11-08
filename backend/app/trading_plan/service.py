"""Evidence-linked AI trade plans + one-week forward paper simulation.

Rules:
- Only AI buy candidates become BUY plans; holdings with negative analysis become SELL plans.
- Market regime gate (breadth up-ratio) decides READY/WATCH and position size; no new
  buys in a weak market (the plan says so instead of pretending it would win).
- Prices: entry = latest snapshot last; stop = -5%; target = +8%; position size
  = weekly capital * 20% (risk 1% / stop 5%), rounded by board lot rules.
- One-week simulation starts on the NEXT trading day; results stay PENDING until
  real future data exists. Never fabricate an outcome.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta, timezone

from ..rules import get_library

TZ = timezone(timedelta(hours=8))
STOP_PCT = 0.05
TARGET_PCT = 0.08
CAPITAL = 100_000.0
POSITION_PCT = 0.20


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def _latest_quote(conn: sqlite3.Connection, code: str) -> dict | None:
    row = conn.execute(
        "SELECT last, prev_close, quote_time, source_id, is_realtime, license_status FROM stock_quotes WHERE code=?",
        (code,),
    ).fetchone()
    return dict(row) if row else None


def _securities(conn: sqlite3.Connection, code: str) -> dict | None:
    row = conn.execute("SELECT exchange, board, name_zh FROM securities WHERE code=?", (code,)).fetchone()
    return dict(row) if row else None


def market_regime(conn: sqlite3.Connection) -> dict:
    breadth = conn.execute(
        "SELECT up_count, down_count, flat_count, quote_time FROM market_breadth ORDER BY fetched_at DESC LIMIT 1"
    ).fetchone()
    if not breadth:
        return {"regime": "UNKNOWN", "up_ratio": None, "size_factor": 0.0, "note": "无涨跌家数数据，暂不新开仓"}
    total = (breadth["up_count"] or 0) + (breadth["down_count"] or 0) + (breadth["flat_count"] or 0)
    up_ratio = (breadth["up_count"] or 0) / total if total else None
    if up_ratio is None:
        regime, factor = "UNKNOWN", 0.0
    elif up_ratio < 0.35:
        regime, factor = "WEAK", 0.0
    elif up_ratio < 0.50:
        regime, factor = "NEUTRAL", 0.5
    else:
        regime, factor = "STRONG", 1.0
    note = {
        "WEAK": "大盘弱势（上涨家数占比<35%），本计划不新开仓，只执行卖出/风控",
        "NEUTRAL": "大盘中性，仓位减半",
        "STRONG": "大盘偏强，正常仓位",
        "UNKNOWN": "无涨跌家数数据，暂不新开仓",
    }[regime]
    return {"regime": regime, "up_ratio": round(up_ratio, 4) if up_ratio is not None else None,
            "size_factor": factor, "note": note, "quote_time": breadth["quote_time"]}


def _round2(value: float) -> float:
    return round(value + 1e-9, 2)


def _lot_qty(conn: sqlite3.Connection, sec: dict, price: float, budget: float, trade_date: date) -> int:
    try:
        _, rules = get_library().select(sec["exchange"], sec["board"], "NORMAL", "SEASONED", trade_date)
    except LookupError:
        return 0
    step = rules.order.step
    qty = int(budget // (price * step)) * step
    if qty < rules.order.min_qty:
        return 0
    return qty


def build_trade_plans(conn: sqlite3.Connection, model_id: str | None = None) -> dict:
    from ..analysis.recommendations import list_recommendations

    regime = market_regime(conn)
    reco_buy = list_recommendations(conn, reco_type="BUY")
    reco_hold = list_recommendations(conn, reco_type="HOLDING")
    today = datetime.now(TZ).date().isoformat()
    plans: list[dict] = []

    with conn:
        conn.execute("UPDATE ai_trade_plans SET status='SUPERSEDED' WHERE status IN ('READY','WATCH','SELL_NOW')")

    def add_plan(reco: dict, action: str, status: str, entry: float | None, qty: int, note: str) -> None:
        current = _latest_quote(conn, reco["code"])
        sec = _securities(conn, reco["code"])
        stop = _round2(entry * (1 - STOP_PCT)) if entry else None
        target = _round2(entry * (1 + TARGET_PCT)) if entry else None
        position_value = round((entry or 0) * qty, 2)
        risk_amount = round((entry - stop) * qty, 2) if entry and stop and qty else 0.0
        risk_pct = round(risk_amount / CAPITAL, 4) if CAPITAL else 0.0
        reasons = list(reco.get("reasons") or []) + ([{"type": "market_regime", "text": note}] if note else [])
        with conn:
            cur = conn.execute(
                """
                INSERT INTO ai_trade_plans(plan_date, code, name, action, status, entry_price, stop_loss,
                    take_profit, qty, position_value, risk_amount, risk_pct, confidence, market_regime,
                    reason_summary, reasons_json, evidence_json, reco_id, model_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    today, reco["code"], reco.get("name"), action, status, entry, stop, target, qty,
                    position_value, risk_amount, risk_pct, reco.get("confidence"), regime["regime"],
                    reco.get("reason_summary"), json.dumps(reasons, ensure_ascii=False),
                    json.dumps(reco.get("evidence") or [], ensure_ascii=False),
                    reco.get("id"), model_id, now_iso(),
                ),
            )
        plan_id = int(cur.lastrowid) if cur.lastrowid else None
        plans.append({"id": plan_id, "code": reco["code"], "action": action, "status": status,
                      "entry": entry, "stop": stop, "target": target, "qty": qty})
        # Detailed in-app notification with exact prices/quantity
        if entry and action == "BUY":
            title = f"交易计划 {reco['code']} {reco.get('name') or ''}：买入 {status}"
            summary = (f"建议买入价 {entry:.2f}（限价不高于此价）；止盈 {target:.2f}；止损 {stop:.2f}；"
                       f"数量 {qty} 股，市值约 {position_value:.0f} 元；大盘状态 {regime['regime']}（{note}）。")
        elif action in ("SELL", "REDUCE"):
            title = f"交易计划 {reco['code']} {reco.get('name') or ''}：{action}"
            summary = f"建议卖出参考价 {entry:.2f}；持仓 {reco.get('position', {}).get('qty') if reco.get('position') else '—'} 股；理由见证据链。"
        else:
            return
        with conn:
            conn.execute(
                "INSERT INTO alerts(level,title,summary,security_codes_json,evidence_json,source_type,source_id,status,triggered_at,updated_at) "
                "VALUES ('L2', ?, ?, ?, ?, 'trade_plan', ?, 'OPEN', ?, ?)",
                (title, summary, json.dumps([reco["code"]]), json.dumps(reco.get("evidence") or [], ensure_ascii=False),
                 plan_id, now_iso(), now_iso()),
            )

    # BUY candidates: market regime gate
    for reco in reco_buy:
        quote = _latest_quote(conn, reco["code"])
        sec = _securities(conn, reco["code"])
        if not quote or not quote.get("last") or not sec:
            continue
        entry = float(quote["last"])
        factor = regime["size_factor"]
        full_budget = CAPITAL * POSITION_PCT
        budget = full_budget * factor
        qty_exec = _lot_qty(conn, sec, entry, budget, datetime.now(TZ).date()) if budget > 0 else 0
        qty_watch = _lot_qty(conn, sec, entry, full_budget, datetime.now(TZ).date())
        if regime["regime"] in ("WEAK", "UNKNOWN"):
            note = regime["note"] + (f"；若转强后按 {qty_watch} 股、买入价 {entry:.2f} 执行" if qty_watch else "")
            add_plan(reco, "BUY", "WATCH", entry, qty_watch, note)
        elif qty_exec <= 0:
            add_plan(reco, "BUY", "WATCH", entry, qty_watch, "资金不足最小申报单位，仅观察")
        else:
            add_plan(reco, "BUY", "READY", entry, qty_exec, regime["note"] + f"；仓位系数 {factor:.1f}")

    # Holdings: sell/reduce plans
    for reco in reco_hold:
        quote = _latest_quote(conn, reco["code"])
        if not quote or not quote.get("last"):
            continue
        entry = float(quote["last"])
        action = reco.get("action")
        if action in ("SELL", "REDUCE"):
            position_qty = int((reco.get("position") or {}).get("qty") or 0)
            add_plan(reco, action, "SELL_NOW", entry, position_qty, "负向新闻证据触发卖出/减仓")
    return {"plan_date": today, "market_regime": regime, "plans": plans}


def list_trade_plans(conn: sqlite3.Connection, limit: int = 100) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM ai_trade_plans WHERE status != 'SUPERSEDED' ORDER BY plan_date DESC, id DESC LIMIT ?",
        (max(1, min(limit, 300)),),
    ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["reasons"] = json.loads(item.pop("reasons_json") or "[]")
        item["evidence"] = json.loads(item.pop("evidence_json") or "[]")
        out.append(item)
    return out


def start_weekly_sim(conn: sqlite3.Connection, initial_cash: float = CAPITAL) -> dict:
    """Start a forward one-week simulation from the next trading day.

    No future prices are invented; plans are PENDING until real daily data arrives.
    """
    from ..trading_calendar import TradingCalendar

    cal = TradingCalendar(conn)
    start = datetime.now(TZ).date()
    for _ in range(10):
        start = start + timedelta(days=1)
        if cal.is_trading_day(start) is True:
            break
    plans = conn.execute(
        "SELECT id, code, entry_price, stop_loss, take_profit, qty, position_value FROM ai_trade_plans "
        "WHERE status IN ('READY','WATCH') AND action='BUY' ORDER BY id DESC LIMIT 5"
    ).fetchall()
    with conn:
        cur = conn.execute(
            "INSERT INTO weekly_sims(name, start_date, initial_cash, cash, benchmark_code, benchmark_start_value, status, note, created_at) "
            "VALUES (?, ?, ?, ?, '000001', NULL, 'PENDING', ?, ?)",
            ("AI一周模拟", start.isoformat(), initial_cash, initial_cash,
             "等待未来交易日数据；不会用历史/编造数据结算", now_iso()),
        )
        sim_id = int(cur.lastrowid)
        for p in plans:
            conn.execute(
                "INSERT OR IGNORE INTO weekly_sim_plans(sim_id, plan_id, code, entry_price, stop_loss, take_profit, qty, position_value, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')",
                (sim_id, p["id"], p["code"], p["entry_price"], p["stop_loss"], p["take_profit"], p["qty"], p["position_value"]),
            )
    return {"sim_id": sim_id, "start_date": start.isoformat(), "plans": len(plans), "status": "PENDING"}


def latest_weekly_sim(conn: sqlite3.Connection) -> dict | None:
    sim = conn.execute("SELECT * FROM weekly_sims ORDER BY id DESC LIMIT 1").fetchone()
    if not sim:
        return None
    plans = conn.execute("SELECT * FROM weekly_sim_plans WHERE sim_id=? ORDER BY id", (sim["id"],)).fetchall()
    marks = conn.execute("SELECT * FROM weekly_sim_marks WHERE sim_id=? ORDER BY trade_date", (sim["id"],)).fetchall()
    return {
        "sim": dict(sim),
        "plans": [dict(p) for p in plans],
        "marks": [dict(m) for m in marks],
        "note": "结果需等待未来 5 个交易日真实数据；当前没有结算不会显示虚构收益。",
    }



def _fee(amount: float, side: str) -> float:
    commission = max(5.0, amount * 0.0003)
    stamp = amount * 0.0005 if side == "SELL" else 0.0
    return round(commission + stamp, 2)


def _simulate(conn: sqlite3.Connection, sim: dict, plans: list[dict], bars_by_code: dict[str, list[dict]],
              index_bars: list[dict]) -> dict:
    """Simulate over real daily bars only; never invents a future price."""
    from datetime import date as _date

    cash = float(sim["initial_cash"])
    initial = float(sim["initial_cash"])
    states: dict[int, dict] = {
        int(p["id"]): {"id": int(p["id"]), "code": p["code"], "qty": p["qty"],
                       "entry_price": None, "stop_loss": p["stop_loss"], "take_profit": p["take_profit"],
                       "entry_date": None, "exit_price": None, "closed_at": None, "pnl": None,
                       "status": "PENDING", "fees": 0.0, "plan_status": p.get("plan_status")}
        for p in plans
    }
    open_ids: set[int] = set()
    plan_rows = {int(p["id"]): p for p in plans}
    start = _date.fromisoformat(sim["start_date"])
    all_dates = sorted({b["date"] for bars in bars_by_code.values() for b in bars if b["date"] >= start.isoformat()})
    index_by_date = {b["date"]: b["close"] for b in index_bars if b["close"]}
    index_dates = sorted(index_by_date)
    start_index = next((index_by_date[d] for d in all_dates if d in index_by_date), None)
    marks = []
    closed_trades = 0

    def bar_for(code: str, day: str) -> dict | None:
        return next((b for b in bars_by_code.get(code, []) if b["date"] == day), None)

    def close_position(pid: int, price: float, day: str) -> None:
        nonlocal cash, closed_trades
        st = states[pid]
        amount = price * st["qty"]
        sell_fee = _fee(amount, "SELL")
        cash += amount - sell_fee
        st["exit_price"] = round(price, 2)
        st["closed_at"] = day
        st["fees"] += sell_fee
        st["pnl"] = round((price - st["entry_price"]) * st["qty"] - st["fees"], 2)
        st["status"] = "CLOSED"
        open_ids.discard(pid)
        closed_trades += 1

    for day in all_dates:
        # exits (T+1: not on the entry date)
        for pid in list(open_ids):
            st = states[pid]
            if day <= st["entry_date"]:
                continue
            bar = bar_for(st["code"], day)
            if not bar:
                continue
            if bar["low"] <= st["stop_loss"]:
                close_position(pid, st["stop_loss"], day)
            elif bar["high"] >= st["take_profit"]:
                close_position(pid, st["take_profit"], day)
            else:
                bars_after = [b for b in bars_by_code.get(st["code"], []) if st["entry_date"] < b["date"] <= day]
                if len(bars_after) >= 5:
                    close_position(pid, bar["close"], day)

        # entries (limit order at plan price; gap-down fills at open)
        for pid, st in states.items():
            if st["status"] != "PENDING":
                continue
            bar = bar_for(st["code"], day)
            if not bar or not st["stop_loss"] or not st["take_profit"] or not st["qty"]:
                continue
            entry = plan_rows[pid]["entry_price"]
            if not entry:
                continue
            # market-alignment filter: only buy when the index is above its 5-day MA
            # (and for WATCH plans also on an up day). This is what "follow the market"
            # means operationally; no entries into a falling tape.
            prior = [index_by_date[d] for d in index_dates if d <= day]
            ma5 = sum(prior[-5:]) / 5 if len(prior) >= 5 else None
            market_ok = True if ma5 is None else index_by_date.get(day, 0) >= ma5
            if st.get("plan_status") == "WATCH" and len(prior) >= 2 and index_by_date.get(day, 0) < prior[-2]:
                market_ok = False
            if not market_ok:
                continue
            if bar["open"] <= entry:
                fill = min(bar["open"], entry)
            elif bar["low"] <= entry <= bar["high"]:
                fill = entry
            else:
                continue
            amount = fill * st["qty"]
            buy_fee = _fee(amount, "BUY")
            if amount + buy_fee > cash:
                st["status"] = "CANCELLED"
                st["note"] = "现金不足"
                continue
            cash -= amount + buy_fee
            st.update({"entry_price": round(fill, 2), "entry_date": day, "status": "OPEN", "fees": buy_fee})
            open_ids.add(pid)

        # mark to market
        mv = 0.0
        for pid in open_ids:
            st = states[pid]
            bar = bar_for(st["code"], day)
            if bar:
                mv += bar["close"] * st["qty"]
        equity = round(cash + mv, 2)
        bench = round(100.0 * index_by_date[day] / start_index, 2) if start_index and day in index_by_date else None
        marks.append({"trade_date": day, "equity": equity, "benchmark_value": bench})

    # end of available data: if >=5 trading days, force-close at last close
    if len(all_dates) >= 5:
        last_day = all_dates[-1]
        for pid in list(open_ids):
            bar = bar_for(states[pid]["code"], last_day)
            close_position(pid, bar["close"] if bar else states[pid]["entry_price"], last_day)
        for st in states.values():
            if st["status"] == "PENDING":
                st["status"] = "CANCELLED"
        # recompute final equity after closes
        final_equity = round(cash, 2)
        if marks:
            marks[-1]["equity"] = final_equity
        status = "CLOSED"
    else:
        final_equity = marks[-1]["equity"] if marks else initial
        status = "ACTIVE" if marks else "PENDING"

    total_return = round((final_equity - initial) / initial, 6) if marks else None
    bench_return = None
    if marks and marks[-1]["benchmark_value"]:
        bench_return = round((marks[-1]["benchmark_value"] - 100) / 100, 6)
    return {
        "cash": round(cash, 2), "equity": final_equity, "total_return": total_return,
        "benchmark_return": bench_return, "status": status, "closed_trades": closed_trades,
        "marks": marks, "plan_results": list(states.values()),
    }


def _fetch_baostock(codes: list[str], start: str, end: str, index: bool = False) -> dict[str, list[dict]]:
    import baostock as bs

    lg = bs.login()
    if lg.error_code != "0":
        raise RuntimeError(f"baostock login failed: {lg.error_msg}")
    out: dict[str, list[dict]] = {}
    try:
        for code in codes:
            if index:
                bs_code = "sh.000001"
            elif code.startswith("6"):
                bs_code = f"sh.{code}"
            elif code.startswith(("0", "3")):
                bs_code = f"sz.{code}"
            else:
                bs_code = f"bj.{code}"
            rs = bs.query_history_k_data_plus(
                bs_code, "date,open,high,low,close", start_date=start, end_date=end,
                frequency="d", adjustflag="2",
            )
            rows = []
            while rs.error_code == "0" and rs.next():
                d = rs.get_row_data()
                try:
                    rows.append({"date": d[0], "open": float(d[1]), "high": float(d[2]),
                                 "low": float(d[3]), "close": float(d[4])})
                except (TypeError, ValueError):
                    continue
            out[code] = rows
    finally:
        bs.logout()
    return out


def evaluate_weekly(conn: sqlite3.Connection, fetch: bool = True) -> dict:
    """Fetch real daily bars and settle the latest started simulation."""
    sim_row = conn.execute("SELECT * FROM weekly_sims ORDER BY id DESC LIMIT 1").fetchone()
    if not sim_row:
        return {"status": "NONE", "message": "尚未启动一周模拟"}
    sim = dict(sim_row)
    plans = [dict(p) for p in conn.execute(
        "SELECT sp.*, tp.status AS plan_status FROM weekly_sim_plans sp "
        "LEFT JOIN ai_trade_plans tp ON tp.id = sp.plan_id WHERE sp.sim_id=? ORDER BY sp.id", (sim["id"],)
    ).fetchall()]
    if not plans:
        return {"status": sim["status"], "message": "该模拟没有计划"}
    if datetime.now(TZ).date().isoformat() < sim["start_date"]:
        return {"status": "PENDING", "message": f"模拟开始日期 {sim['start_date']} 尚未到达，不能提前结算"}
    if not fetch:
        return {"status": "PENDING", "message": "未获取数据"}
    end = datetime.now(TZ).date().isoformat()
    bars = _fetch_baostock([p["code"] for p in plans], sim["start_date"], end)
    index_start = (datetime.fromisoformat(sim["start_date"]) - timedelta(days=10)).date().isoformat()
    index_bars = _fetch_baostock(["000001"], index_start, end, index=True).get("000001", [])
    if not any(bars.values()):
        return {"status": "PENDING", "message": "开始日期后暂无真实日线数据，不结算"}
    result = _simulate(conn, sim, plans, bars, index_bars)
    with conn:
        conn.execute("UPDATE weekly_sims SET cash=?, status=?, note=?, closed_at=? WHERE id=?",
                     (result["cash"], result["status"],
                      f"总收益 {result['total_return']*100:.2f}%；基准 {((result['benchmark_return'] or 0)*100):.2f}%"
                      if result["total_return"] is not None else "等待数据",
                      now_iso() if result["status"] == "CLOSED" else None, sim["id"]))
        for st in result["plan_results"]:
            conn.execute(
                "UPDATE weekly_sim_plans SET status=?, entry_price=?, opened_at=?, closed_at=?, exit_price=?, pnl=? WHERE id=?",
                (st["status"], st["entry_price"], st["entry_date"], st["closed_at"], st["exit_price"], st["pnl"], st["id"]),
            )
        for mark in result["marks"]:
            conn.execute(
                "INSERT OR REPLACE INTO weekly_sim_marks(sim_id, trade_date, equity, benchmark_value, note, created_at) VALUES (?,?,?,?,NULL,?)",
                (sim["id"], mark["trade_date"], mark["equity"], mark["benchmark_value"], now_iso()),
            )
    return {"status": result["status"], "equity": result["equity"], "total_return": result["total_return"],
            "benchmark_return": result["benchmark_return"], "closed_trades": result["closed_trades"],
            "marks": result["marks"], "message": "已按真实日线数据结算"}

