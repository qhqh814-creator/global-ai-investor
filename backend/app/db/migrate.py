"""Simple sequential SQLite migration runner."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def migration_files(directory: Path | None = None) -> list[Path]:
    return sorted((directory or MIGRATIONS_DIR).glob("*.sql"))


def migrate(conn: sqlite3.Connection, directory: Path | None = None) -> list[str]:
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL, checksum TEXT)"
    )
    applied = {row["version"] for row in conn.execute("SELECT version FROM schema_migrations")}
    newly: list[str] = []
    for path in migration_files(directory):
        version = path.name
        if version in applied:
            continue
        sql = path.read_text(encoding="utf-8")
        checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
        with conn:
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_migrations(version, applied_at, checksum) VALUES (?, datetime('now'), ?)",
                (version, checksum),
            )
        newly.append(version)
    return newly
