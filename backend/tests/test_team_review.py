from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta

from backend.app.analysis.team_review import list_team_reviews, run_team_review
from backend.app.analysis.technicals import compute_indicators
from backend.app.db.migrate import migrate

NOW = "2026-11-08T20:00:00+08:00"


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
        "('600000','浦发银行','SSE','MAIN',12.0,1.0,11.9,?,'eastmoney_quote','snapshot_unknown',0,'unlicensed_third_party',0,?)",
        (NOW, NOW),
    )
    start = date(2026, 1, 1)
    for i in range(120):
        d = (start + timedelta(days=i)).isoformat()
        close = 8 + i * 0.03
        conn.execute(
            "INSERT INTO kline_daily(code,trade_date,open,high,low,close,volume,amount,change_pct,adjust_type,source_id,fetched_at) "
            "VALUES ('600000',?,?,?,?,?,?,?,?,'none','test',?)",
            (d, close - 0.05, close + 0.1, close - 0.1, close, 1000 + i, 1e6, 0.2, NOW),
        )
    cur = conn.execute(
        "INSERT INTO news_items(source_id,title,url,summary,published_at,fetched_at,license_status) "
        "VALUES ('chinanews_finance','浦发银行获重大合同','https://example.com/n1','合同金额较大',?,?,'public_page')",
        (NOW, NOW),
    )
    news_id = cur.lastrowid
    conn.execute(
        "INSERT INTO ai_analysis(target_type,target_id,event_type,sentiment,materiality,summary,stocks_json,evidence_json,model_id,created_at) "
        "VALUES ('news',?,'重大合同','positive','L3','获重大合同','[]',?,'test',?)",
        (news_id, json.dumps([{"quote": "浦发银行获重大合同", "source_url": "https://example.com/n1"}], ensure_ascii=False), NOW),
    )
    conn.execute(
        "INSERT INTO news_stock_links(target_type,target_id,code,match_type,confidence,created_at) "
        "VALUES ('news',?,'600000','company_name',0.7,?)", (news_id, NOW)
    )
    conn.commit()
    return conn


class FakeClient:
    def complete_json(self, system_prompt, user_prompt, schema=None):
        return {
            "rating": "BUY",
            "confidence": 0.72,
            "summary": "技术趋势向上，合同消息正面，但财务数据缺失。",
            "technical_view": "价格在MA20上方，趋势偏多。",
            "news_view": "重大合同属正面事件。",
            "risk_view": "缺少财务数据，注意回撤风险。",
            "entry_price": 12.0,
            "target_price": 12.96,
            "stop_loss": 11.4,
            "reasons": ["均线多头", "合同消息"],
            "risks": ["财务数据未提供"],
            "evidence": [{"quote": "获重大合同", "source": "浦发银行获重大合同"}],
        }


def test_technical_indicators_from_trending_bars():
    conn = make_db()
    from backend.app.analysis.technicals import load_bars
    ind = compute_indicators(load_bars(conn, "600000", 120))
    assert ind["ok"] is True
    assert ind["ma20"] and ind["ma5"] > ind["ma20"]
    assert ind["trend"] == "BULLISH"
    assert ind["rsi14"] is not None
    assert ind["macd"] is not None
    assert ind["bb_upper"] > ind["bb_lower"]
    assert ind["atr14"] and ind["atr14"] > 0


def test_team_review_validates_and_persists_evidence():
    conn = make_db()
    result = run_team_review(conn, "600000", FakeClient(), model_id="fake")
    assert result["review"]["rating"] == "BUY"
    assert result["news_count"] == 1
    rows = list_team_reviews(conn, "600000")
    assert len(rows) == 1
    assert rows[0]["evidence"][0]["quote"] == "获重大合同"
    assert rows[0]["indicators"]["trend"] == "BULLISH"


def test_team_review_rejects_fabricated_evidence():
    conn = make_db()

    class Bad(FakeClient):
        def complete_json(self, system_prompt, user_prompt, schema=None):
            payload = super().complete_json(system_prompt, user_prompt, schema)
            payload["evidence"] = [{"quote": "不存在的订单金额10亿元", "source": "x"}]
            return payload

    try:
        run_team_review(conn, "600000", Bad(), model_id="fake")
    except ValueError as exc:
        assert "EVIDENCE_NOT_IN_SOURCE" in str(exc)
    else:
        raise AssertionError("fabricated evidence must be rejected")
