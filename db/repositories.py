from __future__ import annotations

import hashlib
import uuid
from typing import Any

from crawler.models import DownloadResult, ReportMetadata
from db.database import Database, utc_now


class ReportRepository:
    def __init__(self, database: Database):
        self.database = database

    def upsert_report(self, report: ReportMetadata, status: str = "discovered") -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO report_metadata (
                    report_id, ticker, company, title, source, author_org,
                    published_at, report_type, original_url, pdf_url, collected_at,
                    status, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '')
                ON CONFLICT(report_id) DO UPDATE SET
                    ticker = excluded.ticker,
                    company = excluded.company,
                    title = excluded.title,
                    source = excluded.source,
                    author_org = excluded.author_org,
                    published_at = excluded.published_at,
                    report_type = excluded.report_type,
                    original_url = excluded.original_url,
                    pdf_url = excluded.pdf_url,
                    collected_at = excluded.collected_at,
                    status = excluded.status,
                    error_message = ''
                """,
                (
                    report.report_id,
                    report.ticker,
                    report.company,
                    report.title,
                    report.source,
                    report.author_org,
                    report.published_at,
                    report.report_type,
                    report.original_url,
                    report.pdf_url,
                    utc_now(),
                    status,
                ),
            )

    def update_report_status(
        self,
        report_id: str,
        status: str,
        *,
        file_path: str = "",
        error_message: str = "",
    ) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE report_metadata
                SET status = ?, file_path = ?, error_message = ?, collected_at = ?
                WHERE report_id = ?
                """,
                (status, file_path, error_message, utc_now(), report_id),
            )

    def find_by_pdf_url(self, pdf_url: str | None) -> dict[str, Any] | None:
        if not pdf_url:
            return None
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT report_id, pdf_url, file_path FROM report_metadata
                WHERE pdf_url = ? AND status IN ('success', 'duplicate')
                LIMIT 1
                """,
                (pdf_url,),
            ).fetchone()
            if row:
                return dict(row)
            row = connection.execute(
                """
                SELECT report_id, pdf_url, file_path FROM report_files
                WHERE pdf_url = ? AND status IN ('success', 'duplicate')
                LIMIT 1
                """,
                (pdf_url,),
            ).fetchone()
            return dict(row) if row else None

    def find_by_sha256(self, sha256: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT report_id, sha256, file_path FROM report_files
                WHERE sha256 = ? AND status IN ('success', 'duplicate')
                LIMIT 1
                """,
                (sha256,),
            ).fetchone()
            return dict(row) if row else None

    def insert_report_file(
        self,
        report: ReportMetadata,
        result: DownloadResult,
        file_path: str,
        status: str = "success",
        error_message: str = "",
    ) -> None:
        file_id = hashlib.sha256(
            f"{report.report_id}|{result.pdf_hash}|{file_path}".encode("utf-8")
        ).hexdigest()[:24]
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO report_files (
                    file_id, report_id, pdf_url, file_path, sha256, file_size,
                    content_type, is_valid_pdf, downloaded_at, status, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    file_id,
                    report.report_id,
                    report.pdf_url,
                    file_path,
                    result.pdf_hash,
                    result.file_size,
                    result.content_type,
                    1 if result.is_valid_pdf else 0,
                    utc_now(),
                    status,
                    error_message,
                ),
            )

    def insert_target_price_if_present(self, report: ReportMetadata) -> bool:
        if report.target_price is None and not report.investment_opinion:
            return False
        target_price_id = hashlib.sha256(
            f"{report.report_id}|{report.target_price}|{report.investment_opinion}".encode(
                "utf-8"
            )
        ).hexdigest()[:24]
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO target_price_data (
                    target_price_id, report_id, ticker, company, published_at,
                    target_price, investment_opinion, source, author_org,
                    report_type, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    target_price_id,
                    report.report_id,
                    report.ticker,
                    report.company,
                    report.published_at,
                    report.target_price,
                    report.investment_opinion,
                    report.source,
                    report.author_org,
                    report.report_type,
                    utc_now(),
                ),
            )
        return True


class NumericDataRepository:
    def __init__(self, database: Database):
        self.database = database

    def upsert_price_rows(self, rows: list[dict]) -> int:
        with self.database.connect() as connection:
            connection.executemany(
                """
                INSERT OR REPLACE INTO price_data (
                    ticker, company, price_date, open, high, low, close, volume,
                    market_cap, volatility_30d, source, created_at
                ) VALUES (
                    :ticker, :company, :price_date, :open, :high, :low, :close,
                    :volume, :market_cap, :volatility_30d, :source, :created_at
                )
                """,
                rows,
            )
        return len(rows)

    def upsert_macro_rows(self, rows: list[dict]) -> int:
        with self.database.connect() as connection:
            connection.executemany(
                """
                INSERT OR REPLACE INTO macro_data (
                    indicator_id, indicator_name, date, value, unit, frequency,
                    country, source, created_at
                ) VALUES (
                    :indicator_id, :indicator_name, :date, :value, :unit,
                    :frequency, :country, :source, :created_at
                )
                """,
                rows,
            )
        return len(rows)

    def upsert_news_rows(self, rows: list[dict]) -> int:
        with self.database.connect() as connection:
            connection.executemany(
                """
                INSERT OR REPLACE INTO news_metadata (
                    news_id, ticker, company, title, summary, published_at,
                    original_url, source, provider, created_at
                ) VALUES (
                    :news_id, :ticker, :company, :title, :summary, :published_at,
                    :original_url, :source, :provider, :created_at
                )
                """,
                rows,
            )
        return len(rows)

    def upsert_disclosure_rows(self, rows: list[dict]) -> int:
        with self.database.connect() as connection:
            connection.executemany(
                """
                INSERT OR REPLACE INTO disclosure_metadata (
                    disclosure_id, ticker, company, corp_code, report_name,
                    disclosure_type, disclosed_at, receipt_no, original_url,
                    source, created_at
                ) VALUES (
                    :disclosure_id, :ticker, :company, :corp_code, :report_name,
                    :disclosure_type, :disclosed_at, :receipt_no, :original_url,
                    :source, :created_at
                )
                """,
                rows,
            )
        return len(rows)


class RunRepository:
    def __init__(self, database: Database):
        self.database = database

    def start_run(self, source: str) -> str:
        run_id = str(uuid.uuid4())
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO crawler_runs (run_id, source, started_at, status)
                VALUES (?, ?, ?, 'running')
                """,
                (run_id, source, utc_now()),
            )
        return run_id

    def finish_run(
        self,
        run_id: str,
        counts: dict[str, int],
        status: str,
        error_message: str = "",
    ) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE crawler_runs
                SET finished_at = ?, status = ?, total_found = ?,
                    downloaded_count = ?, duplicate_count = ?, failed_count = ?,
                    price_rows_count = ?, macro_rows_count = ?,
                    news_rows_count = ?, disclosure_rows_count = ?,
                    error_message = ?
                WHERE run_id = ?
                """,
                (
                    utc_now(),
                    status,
                    counts.get("total_found", 0),
                    counts.get("downloaded", 0),
                    counts.get("duplicate", 0),
                    counts.get("failed", 0),
                    counts.get("price_rows", 0),
                    counts.get("macro_rows", 0),
                    counts.get("news_rows", 0),
                    counts.get("disclosure_rows", 0),
                    error_message,
                    run_id,
                ),
            )
