CREATE TABLE IF NOT EXISTS ai_trade_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_date TEXT NOT NULL,
    code TEXT NOT NULL,
    name TEXT,
    action TEXT NOT NULL,              -- BUY / SELL / REDUCE / WATCH
    status TEXT NOT NULL,              -- READY / WATCH / SELL_NOW
    entry_price REAL,
    stop_loss REAL,
    take_profit REAL,
    qty INTEGER NOT NULL DEFAULT 0,
    position_value REAL NOT NULL DEFAULT 0,
    risk_amount REAL NOT NULL DEFAULT 0,
    risk_pct REAL NOT NULL DEFAULT 0,
    confidence REAL,
    market_regime TEXT,
    reason_summary TEXT,
    reasons_json TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    reco_id INTEGER,
    model_id TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trade_plans_date ON ai_trade_plans(plan_date, action);

CREATE TABLE IF NOT EXISTS weekly_sims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    start_date TEXT NOT NULL,
    initial_cash REAL NOT NULL,
    cash REAL NOT NULL,
    benchmark_code TEXT,
    benchmark_start_value REAL,
    status TEXT NOT NULL,              -- PENDING / ACTIVE / CLOSED
    note TEXT,
    created_at TEXT NOT NULL,
    closed_at TEXT
);

CREATE TABLE IF NOT EXISTS weekly_sim_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sim_id INTEGER NOT NULL,
    plan_id INTEGER NOT NULL,
    code TEXT NOT NULL,
    entry_price REAL,
    stop_loss REAL,
    take_profit REAL,
    qty INTEGER NOT NULL,
    position_value REAL NOT NULL,
    status TEXT NOT NULL,              -- PENDING / OPEN / CLOSED / CANCELLED
    opened_at TEXT,
    closed_at TEXT,
    exit_price REAL,
    pnl REAL,
    UNIQUE(sim_id, plan_id)
);

CREATE TABLE IF NOT EXISTS weekly_sim_marks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sim_id INTEGER NOT NULL,
    trade_date TEXT NOT NULL,
    equity REAL,
    benchmark_value REAL,
    note TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(sim_id, trade_date)
);
