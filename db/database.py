from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from crawler.models import ReportMetadata


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.schema_path = Path(__file__).with_name("schema.sql")

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(self.schema_path.read_text(encoding="utf-8"))

    def start_run(self) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO collection_runs (started_at) VALUES (?)",
                (utc_now(),),
            )
            return int(cursor.lastrowid)

    def finish_run(
        self,
        run_id: int,
        counts: dict[str, int],
        status: str = "COMPLETED",
        error_message: str = "",
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE collection_runs
                SET finished_at = ?, discovered_count = ?, downloaded_count = ?,
                    duplicated_count = ?, failed_count = ?, status = ?,
                    error_message = ?
                WHERE run_id = ?
                """,
                (
                    utc_now(),
                    counts["discovered"],
                    counts["downloaded"],
                    counts["duplicated"],
                    counts["failed"],
                    status,
                    error_message,
                    run_id,
                ),
            )

    def upsert_discovered(self, report: ReportMetadata) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO reports (
                    report_id, title, securities_firm, published_date, report_type,
                    stock_code, company_name, source_url, pdf_url, collected_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'DISCOVERED')
                ON CONFLICT(report_id) DO UPDATE SET
                    title = excluded.title,
                    securities_firm = excluded.securities_firm,
                    published_date = excluded.published_date,
                    report_type = excluded.report_type,
                    stock_code = excluded.stock_code,
                    company_name = excluded.company_name,
                    source_url = excluded.source_url,
                    pdf_url = excluded.pdf_url,
                    collected_at = excluded.collected_at,
                    error_message = ''
                """,
                (
                    report.report_id,
                    report.title,
                    report.securities_firm,
                    report.published_date,
                    report.report_type,
                    report.stock_code,
                    report.company_name,
                    report.source_url,
                    report.pdf_url,
                    utc_now(),
                ),
            )

    def find_by_pdf_url(self, pdf_url: str) -> sqlite3.Row | None:
        if not pdf_url:
            return None
        with self.connect() as connection:
            return connection.execute(
                """
                SELECT * FROM reports
                WHERE pdf_url = ? AND status IN ('DOWNLOADED', 'DUPLICATED')
                ORDER BY collected_at ASC
                LIMIT 1
                """,
                (pdf_url,),
            ).fetchone()

    def find_by_pdf_hash(self, pdf_hash: str) -> sqlite3.Row | None:
        with self.connect() as connection:
            return connection.execute(
                """
                SELECT * FROM reports
                WHERE pdf_hash = ? AND status IN ('DOWNLOADED', 'DUPLICATED')
                ORDER BY collected_at ASC
                LIMIT 1
                """,
                (pdf_hash,),
            ).fetchone()

    def update_status(
        self,
        report_id: str,
        status: str,
        *,
        pdf_path: str = "",
        pdf_hash: str = "",
        error_message: str = "",
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE reports
                SET status = ?, pdf_path = ?, pdf_hash = ?, error_message = ?,
                    collected_at = ?
                WHERE report_id = ?
                """,
                (
                    status,
                    pdf_path,
                    pdf_hash,
                    error_message,
                    utc_now(),
                    report_id,
                ),
            )

    def get_report(self, report_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM reports WHERE report_id = ?",
                (report_id,),
            ).fetchone()
            return dict(row) if row else None
