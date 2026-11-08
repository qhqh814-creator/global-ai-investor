from __future__ import annotations

import json
import sqlite3

from backend.app.analysis.recommendations import run_recommendations
from backend.app.db.migrate import migrate
from backend.app.trading_plan.service import (
    build_trade_plans,
    latest_weekly_sim,
    list_trade_plans,
    market_regime,
    start_weekly_sim,
)

NOW = "2026-11-08T20:00:00+08:00"
QUOTE_TIME = "2026-11-06T15:00:00+08:00"


def make_db(up=3000, down=1500, flat=500) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    migrate(conn)
    conn.executemany(
        "INSERT INTO securities(code, exchange, board, name_zh, source_id, fetched_at, updated_at) VALUES (?, ?, ?, ?, 'test', ?, ?)",
        [
            ("600000", "SSE", "MAIN", "浦发银行", NOW, NOW),
            ("300001", "SZSE", "CHINEXT", "特锐德", NOW, NOW),
        ],
    )
    conn.execute(
        """
        INSERT INTO stock_quotes(code, name, exchange, board, last, change_pct, prev_close, amount,
            quote_time, source_id, quote_kind, is_realtime, license_status, commercial_ok, fetched_at)
        VALUES ('600000','浦发银行','SSE','MAIN',10.0,1.0,9.9,1e8,?,'eastmoney_quote','snapshot_unknown',0,'unlicensed_third_party',0,?)
        """,
        (QUOTE_TIME, NOW),
    )
    conn.execute(
        "INSERT INTO market_breadth(trade_date,quote_time,up_count,down_count,flat_count,limit_up_count,limit_down_count,"
        "total_amount,source_id,is_realtime,license_status,commercial_ok,note,fetched_at) "
        "VALUES ('2026-11-06',? ,?,?,?,30,10,1.6e12,'eastmoney_quote',0,'unlicensed_third_party',0,NULL,?)",
        (QUOTE_TIME, up, down, flat, NOW),
    )
    conn.commit()
    return conn


def add_positive(conn: sqlite3.Connection) -> None:
    cur = conn.execute(
        "INSERT INTO announcements(announcement_id, sec_code, sec_name, title, published_at, url, source_id, fetched_at) "
        "VALUES ('A1','600000','浦发银行','浦发银行获重大合同',?,'https://example.com/a1','cninfo_announcement',?)",
        (NOW, NOW),
    )
    conn.execute(
        "INSERT INTO ai_analysis(target_type,target_id,event_type,sentiment,materiality,summary,stocks_json,evidence_json,model_id,created_at) "
        "VALUES ('announcement',?,'重大合同','positive','L2','获重大合同，可能增厚业绩。','[]',?,'test-model',?)",
        (cur.lastrowid, json.dumps([{"quote": "浦发银行获重大合同", "source_url": "https://example.com/a1", "published_at": NOW}], ensure_ascii=False), NOW),
    )
    conn.commit()


def add_negative_and_position(conn: sqlite3.Connection) -> None:
    cur = conn.execute(
        "INSERT INTO announcements(announcement_id, sec_code, sec_name, title, published_at, url, source_id, fetched_at) "
        "VALUES ('A2','600000','浦发银行','浦发银行收到立案告知书',?,'https://example.com/a2','cninfo_announcement',?)",
        (NOW, NOW),
    )
    conn.execute(
        "INSERT INTO ai_analysis(target_type,target_id,event_type,sentiment,materiality,summary,stocks_json,evidence_json,model_id,created_at) "
        "VALUES ('announcement',?,'立案调查','negative','L3','公司收到立案告知书，风险上升。','[]',?,'test-model',?)",
        (cur.lastrowid, json.dumps([{"quote": "浦发银行收到立案告知书", "source_url": "https://example.com/a2", "published_at": NOW}], ensure_ascii=False), NOW),
    )
    conn.execute("INSERT INTO sim_accounts(name,initial_cash,cash,created_at) VALUES ('测试账户',100000,90000,?)", (NOW,))
    account_id = conn.execute("SELECT id FROM sim_accounts LIMIT 1").fetchone()["id"]
    conn.execute(
        "INSERT INTO sim_positions(account_id,code,qty,sellable_qty,avg_cost,buy_date,updated_at) VALUES (?,?,1000,0,10.0,'2026-11-01',?)",
        (account_id, "600000", NOW),
    )
    conn.commit()


def test_strong_market_plan_has_exact_prices_and_qty():
    conn = make_db()
    add_positive(conn)
    run_recommendations(conn, model_id="test")
    result = build_trade_plans(conn, model_id="test")
    assert result["market_regime"]["regime"] == "STRONG"
    plans = [p for p in list_trade_plans(conn) if p["action"] == "BUY" and p["code"] == "600000"]
    assert len(plans) == 1
    p = plans[0]
    assert p["status"] == "READY"
    assert p["entry_price"] == 10.0
    assert p["stop_loss"] == 9.5
    assert p["take_profit"] == 10.8
    assert p["qty"] == 2000          # 20% of 100k at 10.00, 100-share board lot
    assert p["position_value"] == 20000.0
    assert p["risk_pct"] == 0.01     # risk 1% of capital (1000 / 100000)


def test_weak_market_blocks_new_buys_but_shows_planned_qty():
    conn = make_db(up=500, down=4000, flat=100)
    add_positive(conn)
    run_recommendations(conn, model_id="test")
    result = build_trade_plans(conn, model_id="test")
    assert result["market_regime"]["regime"] == "WEAK"
    plans = [p for p in list_trade_plans(conn) if p["action"] == "BUY"]
    assert plans and plans[0]["status"] == "WATCH"
    assert plans[0]["qty"] == 2000  # shown for reference, not executed
    assert "不新开仓" in plans[0]["reasons"][-1]["text"]
    sim = start_weekly_sim(conn)
    assert sim["status"] == "PENDING"
    latest = latest_weekly_sim(conn)
    assert latest["sim"]["status"] == "PENDING"
    assert latest["marks"] == []
    assert "不会" in latest["note"]


def test_negative_holding_creates_sell_plan_with_position_qty():
    conn = make_db()
    add_negative_and_position(conn)
    run_recommendations(conn, model_id="test")
    build_trade_plans(conn, model_id="test")
    plans = [p for p in list_trade_plans(conn) if p["action"] in ("SELL", "REDUCE")]
    assert plans
    p = plans[0]
    assert p["status"] == "SELL_NOW"
    assert p["qty"] == 1000
    assert p["entry_price"] == 10.0


def test_weekly_sim_starts_pending_and_never_fabricates_result():
    conn = make_db()
    add_positive(conn)
    run_recommendations(conn, model_id="test")
    build_trade_plans(conn, model_id="test")
    sim = start_weekly_sim(conn)
    assert sim["status"] == "PENDING"
    assert sim["plans"] == 1
    latest = latest_weekly_sim(conn)
    assert latest["sim"]["status"] == "PENDING"
    assert latest["plans"][0]["status"] == "PENDING"
    assert latest["marks"] == []
    assert "total_return" not in latest
    assert latest["sim"]["initial_cash"] == 100000.0

from backend.app.trading_plan.service import _simulate


def _sim():
    return {"initial_cash": 100000.0, "start_date": "2026-11-09"}


def _bars(rows):
    return {"600959": [{"date": d, "open": o, "high": h, "low": l, "close": c} for d, o, h, l, c in rows]}


def _plans():
    return [{"id": 1, "code": "600959", "qty": 1000, "entry_price": 3.23, "stop_loss": 3.07, "take_profit": 3.49}]


def test_sim_target_hit_after_t1_and_fees():
    bars = _bars([
        ("2026-11-09", 3.20, 3.30, 3.18, 3.25),
        ("2026-11-10", 3.30, 3.60, 3.28, 3.55),
    ])
    index = [{"date": "2026-11-09", "close": 4000.0}, {"date": "2026-11-10", "close": 4040.0}]
    r = _simulate(None, _sim(), _plans(), bars, index)
    st = r["plan_results"][0]
    assert st["status"] == "CLOSED"
    assert st["entry_price"] == 3.20          # gap-down limit fill at open
    assert st["exit_price"] == 3.49           # target
    assert st["pnl"] > 0
    assert r["total_return"] > 0
    assert r["benchmark_return"] == 0.01      # 4000 -> 4040


def test_sim_t_plus_one_blocks_same_day_exit():
    # target touched on entry day must NOT sell same day (T+1); sells next day at close.
    bars = _bars([
        ("2026-11-09", 3.20, 3.80, 3.18, 3.60),
        ("2026-11-10", 3.55, 3.60, 3.40, 3.45),
    ])
    r = _simulate(None, _sim(), _plans(), bars, [])
    st = r["plan_results"][0]
    assert st["status"] == "CLOSED"
    assert st["closed_at"] == "2026-11-10"


def test_sim_stop_loss_wins_when_both_touched_same_bar():
    bars = _bars([
        ("2026-11-09", 3.20, 3.30, 3.18, 3.25),
        ("2026-11-10", 3.20, 3.60, 3.00, 3.10),  # both stop 3.07 and target 3.49 touched
    ])
    r = _simulate(None, _sim(), _plans(), bars, [])
    st = r["plan_results"][0]
    assert st["exit_price"] == 3.07
    assert st["pnl"] < 0


def test_sim_without_data_stays_pending_no_fake_return():
    r = _simulate(None, _sim(), _plans(), {}, [])
    assert r["status"] == "PENDING"
    assert r["total_return"] is None
    assert r["marks"] == []


def test_sim_force_closes_after_five_trading_days():
    rows = [
        ("2026-11-09", 3.20, 3.30, 3.18, 3.25),
        ("2026-11-10", 3.25, 3.30, 3.20, 3.26),
        ("2026-11-11", 3.26, 3.30, 3.22, 3.24),
        ("2026-11-12", 3.24, 3.28, 3.20, 3.25),
        ("2026-11-13", 3.25, 3.29, 3.21, 3.27),
        ("2026-11-16", 3.27, 3.30, 3.24, 3.28),
    ]
    r = _simulate(None, _sim(), _plans(), _bars(rows), [])
    st = r["plan_results"][0]
    assert st["status"] == "CLOSED"
    assert st["closed_at"] == "2026-11-16" or st["closed_at"] == "2026-11-13"
    assert r["marks"]

def test_weekly_start_is_idempotent():
    conn = make_db()
    add_positive(conn)
    run_recommendations(conn, model_id="test")
    build_trade_plans(conn, model_id="test")
    first = start_weekly_sim(conn)
    second = start_weekly_sim(conn)
    assert second.get("existing") is True
    assert second["sim_id"] == first["sim_id"]
    n = conn.execute("SELECT COUNT(*) AS n FROM weekly_sims").fetchone()["n"]
    assert n == 1
