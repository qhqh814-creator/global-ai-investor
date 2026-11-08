CREATE TABLE IF NOT EXISTS kline_daily (
    code TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume REAL,
    amount REAL,
    change_pct REAL,
    adjust_type TEXT NOT NULL DEFAULT 'none',
    source_id TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (code, trade_date, adjust_type)
);
CREATE INDEX IF NOT EXISTS idx_kline_code_date ON kline_daily(code, trade_date);

CREATE TABLE IF NOT EXISTS backtests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    params_json TEXT NOT NULL,
    codes_json TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    initial_cash REAL NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS backtest_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    backtest_id INTEGER NOT NULL,
    code TEXT NOT NULL,
    side TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    price REAL NOT NULL,
    qty INTEGER NOT NULL,
    fee_total REAL NOT NULL,
    fee_json TEXT,
    rule_version_id TEXT,
    note TEXT
);
CREATE INDEX IF NOT EXISTS idx_backtest_trades_run ON backtest_trades(backtest_id);

CREATE TABLE IF NOT EXISTS backtest_metrics (
    backtest_id INTEGER PRIMARY KEY,
    total_return REAL,
    annual_return REAL,
    max_drawdown REAL,
    win_rate REAL,
    profit_factor REAL,
    trades_count INTEGER,
    final_equity REAL,
    equity_curve_json TEXT
);

CREATE TABLE IF NOT EXISTS sim_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    initial_cash REAL NOT NULL,
    cash REAL NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sim_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    code TEXT NOT NULL,
    side TEXT NOT NULL,
    order_type TEXT NOT NULL,
    price REAL,
    qty INTEGER NOT NULL,
    status TEXT NOT NULL,
    reject_reason TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sim_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    code TEXT NOT NULL,
    side TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    price REAL NOT NULL,
    qty INTEGER NOT NULL,
    fee_total REAL NOT NULL,
    fee_json TEXT,
    rule_version_id TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sim_positions (
    account_id INTEGER NOT NULL,
    code TEXT NOT NULL,
    qty INTEGER NOT NULL,
    sellable_qty INTEGER NOT NULL,
    avg_cost REAL NOT NULL,
    buy_date TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (account_id, code)
);

CREATE TABLE IF NOT EXISTS sim_nav (
    account_id INTEGER NOT NULL,
    trade_date TEXT NOT NULL,
    total_asset REAL NOT NULL,
    cash REAL NOT NULL,
    market_value REAL NOT NULL,
    pnl REAL NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (account_id, trade_date)
);

CREATE TABLE IF NOT EXISTS ai_predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    direction TEXT NOT NULL,
    horizon_days INTEGER NOT NULL,
    confidence REAL,
    model_id TEXT,
    start_date TEXT NOT NULL,
    start_price REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS prediction_results (
    prediction_id INTEGER PRIMARY KEY,
    settled_at TEXT NOT NULL,
    end_date TEXT NOT NULL,
    end_price REAL NOT NULL,
    actual_change_pct REAL NOT NULL,
    hit INTEGER NOT NULL,
    error_pct REAL
);

CREATE TABLE IF NOT EXISTS accuracy_stats (
    stat_date TEXT NOT NULL,
    scope TEXT NOT NULL,
    model_id TEXT,
    total INTEGER NOT NULL,
    hit INTEGER NOT NULL,
    accuracy REAL NOT NULL,
    avg_error REAL,
    PRIMARY KEY (stat_date, scope, model_id)
);
