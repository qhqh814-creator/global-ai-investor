from __future__ import annotations

import sqlite3

from backend.app.db.migrate import migrate
from backend.app.rules.store import list_versions, stats, sync_library


def make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    migrate(conn)
    return conn


def test_sync_library_persists_versions_and_sets():
    conn = make_db()
    result = sync_library(conn)
    assert result["versions"] == 10
    assert result["rule_sets"] == 96
    assert stats(conn) == {"db_rule_versions": 10, "db_rule_sets": 96}


def test_sync_is_idempotent():
    conn = make_db()
    sync_library(conn)
    sync_library(conn)
    assert stats(conn)["db_rule_sets"] == 96


def test_list_versions_ordered_and_complete():
    conn = make_db()
    sync_library(conn)
    rows = list_versions(conn)
    assert len(rows) == 10
    exchanges = {r["exchange"] for r in rows}
    assert exchanges == {"SSE", "SZSE", "BSE"}
    # each row has a traceable official source URL
    assert all(r["source_url"].startswith("http") for r in rows)
