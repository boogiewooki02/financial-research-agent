from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

from crawler.config import PROJECT_ROOT, Settings
from crawler.kirs_research_crawler import KirsResearchCrawler
from crawler.models import ReportMetadata
from crawler.pdf_downloader import PdfDownloader
from db.database import Database

logger = logging.getLogger(__name__)


class CollectionPipeline:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.database = Database(settings.db_path)
        self.crawler = KirsResearchCrawler(settings)

    def run(self) -> dict[str, int]:
        self.database.initialize()
        run_id = self.database.start_run()
        counts = {"discovered": 0, "downloaded": 0, "duplicated": 0, "failed": 0}
        logger.info("크롤링 시작: %s", self.settings.research_url)

        try:
            reports = asyncio.run(self.crawler.crawl())
            counts["discovered"] = len(reports)
            logger.info("발견한 리포트 수: %s", len(reports))
            self._process_reports(reports, counts)
            self.database.finish_run(run_id, counts)
            logger.info(
                "크롤링 종료 - 발견=%s 신규=%s 중복=%s 실패=%s",
                counts["discovered"],
                counts["downloaded"],
                counts["duplicated"],
                counts["failed"],
            )
            return counts
        except Exception as exc:
            logger.exception("수집 파이프라인 실패: %s", exc)
            self.database.finish_run(
                run_id,
                counts,
                status="FAILED",
                error_message=str(exc),
            )
            raise

    def _process_reports(
        self,
        reports: list[ReportMetadata],
        counts: dict[str, int],
    ) -> None:
        downloader = PdfDownloader(self.settings)
        try:
            for report in reports:
                self._process_one(report, downloader, counts)
        finally:
            downloader.close()

    def _process_one(
        self,
        report: ReportMetadata,
        downloader: PdfDownloader,
        counts: dict[str, int],
    ) -> None:
        self.database.upsert_discovered(report)

        if not report.pdf_url:
            logger.info("PDF 링크 없음, 메타데이터만 저장: %s", report.report_id)
            return

        existing = self.database.find_by_pdf_url(report.pdf_url)
        if existing and existing["report_id"] != report.report_id:
            self.database.update_status(
                report.report_id,
                "DUPLICATED",
                pdf_path=existing["pdf_path"],
                pdf_hash=existing["pdf_hash"],
                error_message=f"동일 pdf_url: {existing['report_id']}",
            )
            counts["duplicated"] += 1
            return
        if existing and existing["report_id"] == report.report_id:
            self.database.update_status(
                report.report_id,
                "DUPLICATED",
                pdf_path=existing["pdf_path"],
                pdf_hash=existing["pdf_hash"],
                error_message="이미 수집된 pdf_url",
            )
            counts["duplicated"] += 1
            return

        final_path = self._build_pdf_path(report)
        try:
            result = downloader.download_to_temp(report.pdf_url, final_path)
            hash_match = self.database.find_by_pdf_hash(result.pdf_hash)
            if hash_match:
                Path(result.temp_path).unlink(missing_ok=True)
                self.database.update_status(
                    report.report_id,
                    "DUPLICATED",
                    pdf_path=hash_match["pdf_path"],
                    pdf_hash=result.pdf_hash,
                    error_message=f"동일 pdf_hash: {hash_match['report_id']}",
                )
                counts["duplicated"] += 1
                return

            downloader.commit(result.temp_path, final_path)
            try:
                stored_path = str(final_path.relative_to(PROJECT_ROOT))
            except ValueError:
                stored_path = str(final_path.resolve())
            self.database.update_status(
                report.report_id,
                "DOWNLOADED",
                pdf_path=stored_path,
                pdf_hash=result.pdf_hash,
            )
            counts["downloaded"] += 1
            logger.info("PDF 저장 완료: %s -> %s", report.report_id, final_path)
        except Exception as exc:
            self.database.update_status(
                report.report_id,
                "FAILED",
                error_message=str(exc),
            )
            counts["failed"] += 1
            logger.exception(
                "리포트 처리 실패: report=%s metadata=%s error=%s",
                report.report_id,
                asdict(report),
                exc,
            )

    def _build_pdf_path(self, report: ReportMetadata) -> Path:
        published = self._parse_date(report.published_date) or date.today()
        return (
            self.settings.pdf_root
            / f"{published.year:04d}"
            / f"{published.month:02d}"
            / f"{published.day:02d}"
            / f"{report.report_id}.pdf"
        )

    @staticmethod
    def _parse_date(value: str) -> date | None:
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return None
