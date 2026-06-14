PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS reports (
    report_id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    securities_firm TEXT NOT NULL DEFAULT '',
    published_date TEXT NOT NULL DEFAULT '',
    report_type TEXT NOT NULL DEFAULT '',
    stock_code TEXT NOT NULL DEFAULT '',
    company_name TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL DEFAULT '',
    pdf_url TEXT NOT NULL DEFAULT '',
    pdf_path TEXT NOT NULL DEFAULT '',
    pdf_hash TEXT NOT NULL DEFAULT '',
    collected_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('DISCOVERED', 'DOWNLOADED', 'DUPLICATED', 'FAILED')
    ),
    error_message TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_reports_pdf_url ON reports(pdf_url);
CREATE INDEX IF NOT EXISTS idx_reports_pdf_hash ON reports(pdf_hash);
CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status);
CREATE INDEX IF NOT EXISTS idx_reports_published_date ON reports(published_date);

CREATE TABLE IF NOT EXISTS collection_runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    discovered_count INTEGER NOT NULL DEFAULT 0,
    downloaded_count INTEGER NOT NULL DEFAULT 0,
    duplicated_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'RUNNING',
    error_message TEXT NOT NULL DEFAULT ''
);

