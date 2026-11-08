CREATE TABLE IF NOT EXISTS news_sources (
    source_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    url TEXT NOT NULL,
    license_status TEXT NOT NULL,
    commercial_ok INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS news_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    summary TEXT,
    published_at TEXT,
    fetched_at TEXT NOT NULL,
    license_status TEXT NOT NULL,
    raw_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_news_published ON news_items(published_at);
CREATE INDEX IF NOT EXISTS idx_news_source ON news_items(source_id);

CREATE TABLE IF NOT EXISTS announcements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    announcement_id TEXT NOT NULL,
    sec_code TEXT,
    sec_name TEXT,
    title TEXT NOT NULL,
    published_at TEXT,
    url TEXT,
    file_url TEXT,
    file_type TEXT,
    file_size_kb INTEGER,
    category TEXT,
    source_id TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    raw_json TEXT,
    UNIQUE(announcement_id, sec_code)
);
CREATE INDEX IF NOT EXISTS idx_announcements_sec ON announcements(sec_code, published_at);
CREATE INDEX IF NOT EXISTS idx_announcements_time ON announcements(published_at);
