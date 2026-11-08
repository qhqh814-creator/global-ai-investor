CREATE TABLE IF NOT EXISTS rule_versions (
    version_code TEXT PRIMARY KEY,
    exchange TEXT NOT NULL,
    doc_no TEXT NOT NULL,
    publish_date TEXT NOT NULL,
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    source_url TEXT NOT NULL,
    checksum TEXT,
    synced_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rule_sets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version_code TEXT NOT NULL,
    exchange TEXT NOT NULL,
    board TEXT NOT NULL,
    risk_flag TEXT NOT NULL,
    listing_phase TEXT NOT NULL,
    params_json TEXT NOT NULL,
    synced_at TEXT NOT NULL,
    UNIQUE(version_code, board, risk_flag, listing_phase)
);
CREATE INDEX IF NOT EXISTS idx_rule_sets_lookup ON rule_sets(exchange, board, risk_flag, listing_phase);
CREATE INDEX IF NOT EXISTS idx_rule_versions_effective ON rule_versions(exchange, effective_from, effective_to);
