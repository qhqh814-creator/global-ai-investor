from __future__ import annotations

import sqlite3

from backend.app.ai.clients import AiConfig, AiUnavailable, DeepSeekClient
from backend.app.ai.service import (
    acknowledge_alert,
    ai_status,
    analyze_pending,
    ensure_alert_rules,
    list_alerts,
    list_analysis,
)
from backend.app.db.migrate import migrate

NOW = "2026-11-07T10:00:00+08:00"


class FakeClient:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.available_flag = True

    def available(self) -> bool:
        return self.available_flag

    def analyze(self, prompt: str) -> dict:
        return self.payloads.pop(0)


def make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    migrate(conn)
    conn.execute(
        """
        INSERT INTO news_items(source_id, title, url, summary, published_at, fetched_at, license_status)
        VALUES ('chinanews_finance', '央行开展逆回购操作', 'https://example.com/1',
                '为维护银行体系流动性合理充裕，央行今日开展逆回购操作。', ?, ?, 'public_page')
        """,
        (NOW, NOW),
    )
    conn.execute(
        """
        INSERT INTO news_items(source_id, title, url, summary, published_at, fetched_at, license_status)
        VALUES ('chinanews_finance', '公司发布业绩预告', 'https://example.com/2',
                '公司预计净利润同比增长50%。', ?, ?, 'public_page')
        """,
        (NOW, NOW),
    )
    conn.commit()
    return conn


def valid_payload(quote: str, materiality: str = "L3") -> dict:
    return {
        "event_type": "公开市场操作",
        "sentiment": "neutral",
        "materiality": materiality,
        "summary": "央行开展逆回购操作，流动性保持合理充裕。",
        "stocks": [],
        "evidence": [
            {"quote": quote, "source_url": "https://example.com/1", "published_at": NOW}
        ],
    }


def test_analyze_creates_analysis_and_alert():
    conn = make_db()
    client = FakeClient(
        [
            valid_payload("央行今日开展逆回购操作", "L3"),
            valid_payload("公司预计净利润同比增长50%", "L1"),
        ]
    )
    result = analyze_pending(conn, client, limit=10, model_id="fake")
    assert result["analyzed"] == 2
    assert result["alerts"] == 1
    assert len(list_analysis(conn)) == 2
    alerts = list_alerts(conn)
    assert len(alerts) == 1 and alerts[0]["level"] == "L3"
    status = ai_status(conn, client)
    assert status["counts"]["ai_analysis"] == 2


def test_evidence_must_come_from_source():
    conn = make_db()
    client = FakeClient([valid_payload("完全不存在于原文的句子", "L3")])
    result = analyze_pending(conn, client, limit=1, model_id="fake")
    assert result["analyzed"] == 0
    assert result["failures"]
    tasks = conn.execute("SELECT status, error FROM ai_tasks").fetchall()
    assert tasks[0]["status"] == "FAILED"
    assert "EVIDENCE_NOT_IN_SOURCE" in tasks[0]["error"]
    assert len(list_analysis(conn)) == 0


def test_invalid_schema_fails_task():
    conn = make_db()

    class BadJsonClient(FakeClient):
        def analyze(self, prompt: str) -> dict:
            raise ValueError("invalid json")

    client = BadJsonClient([])
    result = analyze_pending(conn, client, limit=1, model_id="fake")
    assert result["analyzed"] == 0
    assert result["failures"]


def test_deepseek_without_key_unavailable():
    client = DeepSeekClient(AiConfig(provider="deepseek", api_key=None))
    assert client.available() is False
    try:
        client.analyze("x")
        assert False, "expected AiUnavailable"
    except AiUnavailable:
        pass


def test_alert_rules_seeded_and_ack():
    conn = make_db()
    ensure_alert_rules(conn)
    levels = {r["level"] for r in conn.execute("SELECT level FROM alert_rules").fetchall()}
    assert levels == {"L1", "L2", "L3", "L4"}

    client = FakeClient([valid_payload("央行今日开展逆回购操作", "L3")])
    analyze_pending(conn, client, limit=1)
    alert = list_alerts(conn)[0]
    assert acknowledge_alert(conn, alert["id"]) is True
    assert list_alerts(conn)[0]["status"] == "ACK"
