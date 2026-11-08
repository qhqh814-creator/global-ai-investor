CREATE TABLE IF NOT EXISTS global_news (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    summary TEXT,
    published_at TEXT,
    language TEXT NOT NULL DEFAULT 'en',
    keywords TEXT,
    license_status TEXT NOT NULL DEFAULT 'public_page',
    fetched_at TEXT NOT NULL,
    raw_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_global_news_time ON global_news(published_at);

CREATE TABLE IF NOT EXISTS news_verification (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_type TEXT NOT NULL,
    target_id INTEGER NOT NULL,
    source_authenticity TEXT NOT NULL,
    corroboration_count INTEGER NOT NULL DEFAULT 1,
    price_reaction TEXT NOT NULL,
    price_detail_json TEXT,
    stock_codes_json TEXT,
    verified_at TEXT NOT NULL,
    UNIQUE(target_type, target_id)
);
CREATE INDEX IF NOT EXISTS idx_news_verification_reaction ON news_verification(price_reaction);

CREATE TABLE IF NOT EXISTS daily_picks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pick_date TEXT NOT NULL,
    week_start TEXT NOT NULL,
    code TEXT NOT NULL,
    name TEXT,
    pick_type TEXT NOT NULL,              -- BUY / SELL
    entry_price REAL,
    target_price REAL,
    stop_loss REAL,
    qty INTEGER,
    reason TEXT,
    evidence_json TEXT,
    verification_json TEXT,
    model_id TEXT,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at TEXT NOT NULL,
    UNIQUE(pick_date, code, pick_type)
);
CREATE INDEX IF NOT EXISTS idx_daily_picks_week ON daily_picks(week_start, pick_type);

CREATE TABLE IF NOT EXISTS weekly_focus (
    week_start TEXT NOT NULL,
    code TEXT NOT NULL,
    name TEXT,
    pick_type TEXT NOT NULL,
    locked_at TEXT NOT NULL,
    PRIMARY KEY (week_start, code, pick_type)
);
