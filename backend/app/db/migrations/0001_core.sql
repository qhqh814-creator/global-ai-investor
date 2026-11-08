CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL,
    checksum TEXT
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trading_calendar (
    trade_date TEXT PRIMARY KEY,
    is_trading_day INTEGER NOT NULL CHECK (is_trading_day IN (0, 1)),
    source_id TEXT NOT NULL,
    year INTEGER NOT NULL,
    note TEXT,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_calendar_year ON trading_calendar(year);

CREATE TABLE IF NOT EXISTS data_sources (
    source_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    base_url TEXT,
    license_status TEXT NOT NULL,
    commercial_ok INTEGER NOT NULL DEFAULT 0,
    latency_class TEXT NOT NULL DEFAULT 'unknown',
    enabled INTEGER NOT NULL DEFAULT 1,
    config_json TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS data_fetch_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    status_code INTEGER,
    duration_ms INTEGER,
    records_count INTEGER,
    error_code TEXT,
    fetched_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fetch_log_source_time ON data_fetch_log(source_id, fetched_at);
