"""Persist the file-based rule library into SQLite for audit/query (P1)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from .loader import get_library


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def sync_library(conn: sqlite3.Connection) -> dict:
    lib = get_library()
    ts = now_iso()
    versions = 0
    sets = 0
    with conn:
        for version in lib.versions:
            conn.execute(
                """
                INSERT INTO rule_versions(
                    version_code, exchange, doc_no, publish_date, effective_from,
                    effective_to, source_url, checksum, synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(version_code) DO UPDATE SET
                    exchange=excluded.exchange,
                    doc_no=excluded.doc_no,
                    publish_date=excluded.publish_date,
                    effective_from=excluded.effective_from,
                    effective_to=excluded.effective_to,
                    source_url=excluded.source_url,
                    checksum=excluded.checksum,
                    synced_at=excluded.synced_at
                """,
                (
                    version.version_code,
                    version.exchange,
                    version.doc_no,
                    version.publish_date.isoformat(),
                    version.effective_from.isoformat(),
                    version.effective_to.isoformat() if version.effective_to else None,
                    version.source_url,
                    version.checksum,
                    ts,
                ),
            )
            versions += 1
            for board, board_rules in version.boards.items():
                for rules in board_rules.sets:
                    conn.execute(
                        """
                        INSERT INTO rule_sets(
                            version_code, exchange, board, risk_flag, listing_phase, params_json, synced_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(version_code, board, risk_flag, listing_phase) DO UPDATE SET
                            params_json=excluded.params_json,
                            synced_at=excluded.synced_at
                        """,
                        (
                            version.version_code,
                            version.exchange,
                            board,
                            rules.risk_flag,
                            rules.listing_phase,
                            json.dumps(rules.model_dump(), ensure_ascii=False),
                            ts,
                        ),
                    )
                    sets += 1
    return {"versions": versions, "rule_sets": sets}


def stats(conn: sqlite3.Connection) -> dict:
    row = conn.execute("SELECT COUNT(*) AS n FROM rule_versions").fetchone()
    row2 = conn.execute("SELECT COUNT(*) AS n FROM rule_sets").fetchone()
    return {"db_rule_versions": int(row["n"]), "db_rule_sets": int(row2["n"])}


def list_versions(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT version_code, exchange, doc_no, effective_from, effective_to, source_url "
        "FROM rule_versions ORDER BY exchange, effective_from"
    ).fetchall()
    return [dict(r) for r in rows]
