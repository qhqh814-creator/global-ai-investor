CREATE TABLE IF NOT EXISTS ai_team_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    as_of TEXT NOT NULL,
    rating TEXT NOT NULL,
    confidence REAL,
    summary TEXT,
    technical_view TEXT,
    news_view TEXT,
    risk_view TEXT,
    decision_json TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    indicators_json TEXT NOT NULL,
    model_id TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(code, as_of, model_id)
);
CREATE INDEX IF NOT EXISTS idx_team_reviews_code ON ai_team_reviews(code, created_at);
