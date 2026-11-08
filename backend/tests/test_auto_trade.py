from __future__ import annotations

import json
import sqlite3

from backend.app.auto_trade.service import auto_buy_ready, risk_check
from backend.app.db.migrate import migrate

NOW = "2026-11-08T20:00:00+08:00"
QUOTE_TIME = "2026-11-06T15:00:00+08:00"


def make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    migrate(conn)
    conn.execute(
        "INSERT INTO securities(code,exchange,board,name_zh,source_id,fetched_at,updated_at) "
        "VALUES ('600000','SSE','MAIN','浦发银行','test',?,?)", (NOW, NOW)
    )
    conn.execute(
        "INSERT INTO stock_quotes(code,name,exchange,board,last,change_pct,prev_close,quote_time,source_id,"
        "quote_kind,is_realtime,license_status,commercial_ok,fetched_at) VALUES "
        "('600000','浦发银行','SSE','MAIN',10.0,1.0,9.9,?,'eastmoney_quote','snapshot_unknown',0,'unlicensed_third_party',0,?)",
        (QUOTE_TIME, NOW),
    )
    conn.execute(
        "INSERT INTO ai_trade_plans(plan_date,code,name,action,status,entry_price,stop_loss,take_profit,qty,"
        "position_value,risk_amount,risk_pct,confidence,market_regime,reason_summary,reasons_json,evidence_json,"
        "reco_id,model_id,created_at) VALUES ('2026-11-06','600000','浦发银行','BUY','READY',10.0,9.5,10.8,"
        "100,1000,50,0.001,0.6,'STRONG','test','[]','[]',NULL,'test',?)", (NOW,)
    )
    conn.commit()
    return conn


def test_auto_buy_ready_places_order():
    conn = make_db()
    result = auto_buy_ready(conn, refresh=False)
    assert result["placed"] == 1
    pos = conn.execute("SELECT qty,avg_cost FROM sim_positions WHERE code='600000'").fetchone()
    assert pos["qty"] == 100
    assert pos["avg_cost"] > 0


def test_risk_check_stop_loss_sells_sellable_position():
    conn = make_db()
    auto_buy_ready(conn, refresh=False)
    # make it sellable next day and drop price below -8%
    with conn:
        conn.execute("UPDATE sim_positions SET buy_date='2026-11-05', sellable_qty=100 WHERE code='600000'")
        conn.execute("UPDATE stock_quotes SET last=9.0, prev_close=9.1, quote_time='2026-11-06T15:00:00+08:00' WHERE code='600000'")
    result = risk_check(conn)
    assert result["sold"] == 1
    assert conn.execute("SELECT COUNT(*) FROM sim_positions").fetchone()[0] == 0


def test_risk_check_negative_news_sells_position():
    conn = make_db()
    auto_buy_ready(conn, refresh=False)
    with conn:
        conn.execute("UPDATE sim_positions SET buy_date='2026-11-05', sellable_qty=100 WHERE code='600000'")
        conn.execute(
            "INSERT INTO news_items(source_id,title,url,summary,published_at,fetched_at,license_status) "
            "VALUES ('chinanews_finance','浦发银行遭立案','https://example.com/n1','立案调查',?,?,'public_page')",
            (NOW, NOW),
        )
        news_id = conn.execute("SELECT id FROM news_items").fetchone()["id"]
        conn.execute(
            "INSERT INTO ai_analysis(target_type,target_id,event_type,sentiment,materiality,summary,stocks_json,evidence_json,model_id,created_at) "
            "VALUES ('news',?,'立案调查','negative','L4','公司被立案，风险重大','[]','[]','test',?)",
            (news_id, NOW),
        )
        conn.execute(
            "INSERT INTO news_stock_links(target_type,target_id,code,match_type,confidence,created_at) "
            "VALUES ('news',?,'600000','company_name',0.8,?)", (news_id, NOW)
        )
    result = risk_check(conn)
    assert result["sold"] == 1
    assert conn.execute("SELECT COUNT(*) FROM sim_positions").fetchone()[0] == 0


def test_risk_check_market_crash_sells_all():
    conn = make_db()
    auto_buy_ready(conn, refresh=False)
    with conn:
        conn.execute("UPDATE sim_positions SET buy_date='2026-11-05', sellable_qty=100 WHERE code='600000'")
        conn.execute(
            "INSERT INTO market_breadth(trade_date,quote_time,up_count,down_count,flat_count,limit_up_count,"
            "limit_down_count,total_amount,source_id,is_realtime,license_status,commercial_ok,note,fetched_at) "
            "VALUES ('2026-11-06',?,100,900,0,5,50,1e12,'eastmoney_quote',0,'unlicensed_third_party',0,NULL,?)",
            (QUOTE_TIME, NOW),
        )
    result = risk_check(conn)
    assert result["crash"] is True
    assert result["sold"] == 1
