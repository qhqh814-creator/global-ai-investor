from __future__ import annotations

import sqlite3

from backend.app.db.migrate import migrate
from backend.app.pipeline.service import run_pipeline, status

NOW = "2026-11-08T20:00:00+08:00"


class FakeClient:
    def __init__(self, payload):
        self.payload = payload

    def available(self) -> bool:
        return True

    def analyze(self, prompt: str) -> dict:
        return self.payload


def make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    migrate(conn)
    conn.execute(
        "INSERT INTO news_items(source_id,title,url,summary,published_at,fetched_at,license_status) "
        "VALUES ('chinanews_finance','某公司获重大合同','https://example.com/n1','合同金额较大','2026-11-08T09:00:00+08:00',?,'public_page')",
        (NOW,),
    )
    conn.commit()
    return conn


def test_pipeline_status_counts():
    conn = make_db()
    s = status(conn)
    assert s["news_count"] == 1
    assert s["pending_analysis"] == 1
    assert s["analyzed_count"] == 0
    assert s["weekly"] is None


def test_run_pipeline_analyzes_then_creates_simulation():
    conn = make_db()
    payload = {
        "event_type": "重大合同", "sentiment": "positive", "materiality": "L1",
        "summary": "公司获重大合同。", "stocks": [],
        "evidence": [{"quote": "某公司获重大合同", "source_url": "https://example.com/n1", "published_at": NOW}],
    }
    result = run_pipeline(conn, collect=False, analyze_limit=1, client=FakeClient(payload))
    keys = [s["key"] for s in result["stages"]]
    assert keys == ["verify", "analyze", "opportunities", "plans", "simulate"]
    assert all(s["status"] == "ok" for s in result["stages"])
    assert result["analyzed_count"] == 1
    assert result["pending_analysis"] == 0
    assert result["weekly"] is not None
    assert result["weekly"]["sim"]["status"] == "PENDING"

