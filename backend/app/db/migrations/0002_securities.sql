CREATE TABLE IF NOT EXISTS securities (
    code TEXT PRIMARY KEY,
    exchange TEXT NOT NULL,
    board TEXT NOT NULL,
    security_type TEXT NOT NULL DEFAULT 'STOCK',
    name_zh TEXT NOT NULL,
    name_en TEXT,
    listing_date TEXT,
    status TEXT NOT NULL DEFAULT 'NORMAL',
    total_shares INTEGER,
    float_shares INTEGER,
    industry TEXT,
    source_id TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    raw_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_securities_exchange_board ON securities(exchange, board);

CREATE TABLE IF NOT EXISTS security_status_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    status TEXT NOT NULL,
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    source_id TEXT,
    note TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_status_history_code ON security_status_history(code, effective_from);
