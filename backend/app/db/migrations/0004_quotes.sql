CREATE TABLE IF NOT EXISTS index_quotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    index_code TEXT NOT NULL,
    name TEXT NOT NULL,
    quote_time TEXT NOT NULL,
    last REAL,
    change REAL,
    change_pct REAL,
    source_id TEXT NOT NULL,
    quote_kind TEXT NOT NULL,
    is_realtime INTEGER NOT NULL DEFAULT 0,
    license_status TEXT NOT NULL,
    commercial_ok INTEGER NOT NULL DEFAULT 0,
    fetched_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_index_quotes_time ON index_quotes(index_code, quote_time);

CREATE TABLE IF NOT EXISTS stock_quotes (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    exchange TEXT NOT NULL,
    board TEXT NOT NULL,
    last REAL,
    change_pct REAL,
    prev_close REAL,
    amount REAL,
    market_cap REAL,
    quote_time TEXT,
    source_id TEXT NOT NULL,
    quote_kind TEXT NOT NULL,
    is_realtime INTEGER NOT NULL DEFAULT 0,
    license_status TEXT NOT NULL,
    commercial_ok INTEGER NOT NULL DEFAULT 0,
    fetched_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_stock_quotes_board ON stock_quotes(exchange, board);

CREATE TABLE IF NOT EXISTS market_breadth (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date TEXT NOT NULL,
    quote_time TEXT,
    up_count INTEGER NOT NULL,
    down_count INTEGER NOT NULL,
    flat_count INTEGER NOT NULL,
    limit_up_count INTEGER NOT NULL,
    limit_down_count INTEGER NOT NULL,
    total_amount REAL NOT NULL,
    source_id TEXT NOT NULL,
    is_realtime INTEGER NOT NULL DEFAULT 0,
    license_status TEXT NOT NULL,
    commercial_ok INTEGER NOT NULL DEFAULT 0,
    note TEXT,
    fetched_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_market_breadth_time ON market_breadth(trade_date, fetched_at);

CREATE TABLE IF NOT EXISTS data_availability (
    data_key TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    reason_code TEXT,
    detail TEXT,
    last_success_at TEXT,
    updated_at TEXT NOT NULL
);
