CREATE TABLE IF NOT EXISTS news_stock_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_type TEXT NOT NULL,
    target_id INTEGER NOT NULL,
    code TEXT NOT NULL,
    match_type TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.5,
    created_at TEXT NOT NULL,
    UNIQUE(target_type, target_id, code)
);
CREATE INDEX IF NOT EXISTS idx_news_stock_links_code ON news_stock_links(code, target_type);

CREATE TABLE IF NOT EXISTS recommendation_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id TEXT,
    params_json TEXT,
    stats_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER,
    reco_type TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    code TEXT NOT NULL,
    name TEXT,
    action TEXT NOT NULL,
    confidence REAL,
    score REAL,
    horizon_days INTEGER,
    reason_summary TEXT,
    reasons_json TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    source_analysis_json TEXT,
    quote_json TEXT,
    position_json TEXT,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    model_id TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(reco_type, code, trade_date, run_id)
);
CREATE INDEX IF NOT EXISTS idx_ai_reco_type_date ON ai_recommendations(reco_type, trade_date);
CREATE INDEX IF NOT EXISTS idx_ai_reco_code ON ai_recommendations(code);

