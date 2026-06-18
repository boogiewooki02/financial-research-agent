PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS report_metadata (
    report_id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL DEFAULT '',
    company TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    author_org TEXT NOT NULL DEFAULT '',
    published_at TEXT NOT NULL DEFAULT '',
    report_type TEXT NOT NULL DEFAULT 'unknown',
    original_url TEXT NOT NULL DEFAULT '',
    pdf_url TEXT,
    file_path TEXT NOT NULL DEFAULT '',
    collected_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('discovered', 'success', 'failed', 'duplicate', 'no_pdf_url')
    ),
    error_message TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_report_metadata_pdf_url ON report_metadata(pdf_url);
CREATE INDEX IF NOT EXISTS idx_report_metadata_ticker ON report_metadata(ticker);
CREATE INDEX IF NOT EXISTS idx_report_metadata_published_at ON report_metadata(published_at);
CREATE INDEX IF NOT EXISTS idx_report_metadata_status ON report_metadata(status);

CREATE TABLE IF NOT EXISTS report_files (
    file_id TEXT PRIMARY KEY,
    report_id TEXT NOT NULL,
    pdf_url TEXT,
    file_path TEXT NOT NULL DEFAULT '',
    sha256 TEXT NOT NULL DEFAULT '',
    file_size INTEGER NOT NULL DEFAULT 0,
    content_type TEXT NOT NULL DEFAULT '',
    is_valid_pdf INTEGER NOT NULL DEFAULT 0,
    downloaded_at TEXT NOT NULL,
    status TEXT NOT NULL,
    error_message TEXT NOT NULL DEFAULT '',
    FOREIGN KEY(report_id) REFERENCES report_metadata(report_id)
);

CREATE INDEX IF NOT EXISTS idx_report_files_pdf_url ON report_files(pdf_url);
CREATE INDEX IF NOT EXISTS idx_report_files_sha256 ON report_files(sha256);

CREATE TABLE IF NOT EXISTS target_price_data (
    target_price_id TEXT PRIMARY KEY,
    report_id TEXT NOT NULL,
    ticker TEXT NOT NULL DEFAULT '',
    company TEXT NOT NULL DEFAULT '',
    published_at TEXT NOT NULL DEFAULT '',
    target_price REAL,
    investment_opinion TEXT,
    source TEXT NOT NULL DEFAULT '',
    author_org TEXT NOT NULL DEFAULT '',
    report_type TEXT NOT NULL DEFAULT 'unknown',
    created_at TEXT NOT NULL,
    FOREIGN KEY(report_id) REFERENCES report_metadata(report_id)
);

CREATE TABLE IF NOT EXISTS price_data (
    ticker TEXT NOT NULL,
    company TEXT NOT NULL DEFAULT '',
    price_date TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume INTEGER,
    market_cap REAL,
    volatility_30d REAL,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (ticker, price_date, source)
);

CREATE TABLE IF NOT EXISTS macro_data (
    indicator_id TEXT NOT NULL,
    indicator_name TEXT NOT NULL DEFAULT '',
    date TEXT NOT NULL,
    value REAL,
    unit TEXT NOT NULL DEFAULT '',
    frequency TEXT NOT NULL DEFAULT '',
    country TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (indicator_id, date, source)
);

CREATE TABLE IF NOT EXISTS crawler_runs (
    run_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    total_found INTEGER NOT NULL DEFAULT 0,
    downloaded_count INTEGER NOT NULL DEFAULT 0,
    duplicate_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    price_rows_count INTEGER NOT NULL DEFAULT 0,
    macro_rows_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT NOT NULL DEFAULT ''
);
