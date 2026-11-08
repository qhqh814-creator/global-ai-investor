CREATE TABLE IF NOT EXISTS watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS watchlist_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    watchlist_id INTEGER NOT NULL,
    code TEXT NOT NULL,
    note TEXT,
    added_at TEXT NOT NULL,
    UNIQUE(watchlist_id, code)
);
CREATE INDEX IF NOT EXISTS idx_watchlist_items_list ON watchlist_items(watchlist_id);

CREATE TABLE IF NOT EXISTS signal_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    side TEXT NOT NULL,
    condition_json TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER NOT NULL,
    code TEXT NOT NULL,
    side TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    price REAL,
    change_pct REAL,
    rule_version_id TEXT,
    evidence_json TEXT,
    triggered_at TEXT NOT NULL,
    UNIQUE(rule_id, code, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_signals_date ON signals(trade_date);

CREATE TABLE IF NOT EXISTS screening_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    filters_json TEXT NOT NULL,
    status TEXT NOT NULL,
    result_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS screening_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    code TEXT NOT NULL,
    score REAL,
    reasons_json TEXT,
    UNIQUE(run_id, code)
);
CREATE INDEX IF NOT EXISTS idx_screening_results_run ON screening_results(run_id);
