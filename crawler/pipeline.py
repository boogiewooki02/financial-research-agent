from __future__ import annotations

import asyncio
import logging
from datetime import date
from pathlib import Path
from typing import Iterable

from collectors.macro_data_collector import MacroDataCollector
from collectors.price_data_collector import PriceDataCollector
from config.report_type_codes import normalize_report_type
from config.settings import PROJECT_ROOT, Settings
from config.supported_companies import SUPPORTED_COMPANIES, resolve_company_from_text
from crawler.base_crawler import is_within_months, parse_date
from crawler.kirs_research_crawler import KirsResearchCrawler
from crawler.models import ReportMetadata
from crawler.naver_research_crawler import NaverResearchCrawler
from crawler.pdf_downloader import PdfDownloader
from db.database import Database
from db.repositories import NumericDataRepository, ReportRepository, RunRepository

logger = logging.getLogger(__name__)


class CollectionPipeline:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.database = Database(settings.db_path)
        self.reports = ReportRepository(self.database)
        self.numeric_data = NumericDataRepository(self.database)
        self.runs = RunRepository(self.database)

    def run(self) -> dict[str, int]:
        self.database.initialize()
        return self.run_collection(self.settings.source)

    def run_collection(self, source: str) -> dict[str, int]:
        run_id = self.runs.start_run(source)
        counts = {
            "total_found": 0,
            "downloaded": 0,
            "duplicate": 0,
            "failed": 0,
            "price_rows": 0,
            "macro_rows": 0,
            "target_rows": 0,
        }
        logger.info("수집 시작: source=%s", source)

        try:
            reports = self._collect_reports(source)
            scoped_reports = self._limit_collection_scope(reports)
            counts["total_found"] = len(scoped_reports)
            self._process_reports(scoped_reports, counts)
            self._collect_numeric_data(counts)
            status = "partial" if counts["failed"] else "success"
            self.runs.finish_run(run_id, counts, status)
            logger.info(
                "수집 종료: source=%s found=%s downloaded=%s duplicate=%s failed=%s "
                "target=%s price_rows=%s macro_rows=%s",
                source,
                counts["total_found"],
                counts["downloaded"],
                counts["duplicate"],
                counts["failed"],
                counts["target_rows"],
                counts["price_rows"],
                counts["macro_rows"],
            )
            return counts
        except Exception as exc:
            logger.exception("수집 파이프라인 실패: %s", exc)
            self.runs.finish_run(run_id, counts, "failed", str(exc))
            raise

    def _collect_reports(self, source: str) -> list[ReportMetadata]:
        selected_sources = ["naver", "kirs"] if source == "all" else [source]
        reports: list[ReportMetadata] = []
        for selected_source in selected_sources:
            if selected_source == "naver":
                reports.extend(self._collect_naver_reports())
            elif selected_source == "kirs":
                reports.extend(self._collect_kirs_reports())
        return self._deduplicate_reports(reports)

    def _collect_naver_reports(self) -> list[ReportMetadata]:
        crawler = NaverResearchCrawler(self.settings)
        reports: list[ReportMetadata] = []
        for company in SUPPORTED_COMPANIES:
            rows = crawler.fetch_reports_for_company(
                company["ticker"],
                company["company"],
                months=self.settings.months,
                max_pages=self.settings.max_pages,
            )
            logger.info(
                "기업별 발견 리포트 수: source=NAVER company=%s count=%s",
                company["company"],
                len(rows),
            )
            reports.extend(ReportMetadata(**row) for row in rows)
        return reports

    def _collect_kirs_reports(self) -> list[ReportMetadata]:
        try:
            raw_reports = asyncio.run(KirsResearchCrawler(self.settings).crawl())
        except Exception as exc:
            logger.warning("KIRS 수집 실패: %s", exc)
            return []

        reports: list[ReportMetadata] = []
        for report in raw_reports:
            resolved = resolve_company_from_text(
                f"{report.ticker} {report.company} {report.title}"
            )
            if resolved is None:
                report.report_type = normalize_report_type(report.report_type, report.title)
                report.source = report.source or "KIRS"
                reports.append(report)
                continue
            report.ticker = resolved["ticker"]
            report.company = resolved["company"]
            report.report_type = normalize_report_type(report.report_type, report.title)
            reports.append(report)
        logger.info("KIRS 발견 리포트 수: %s", len(reports))
        return reports

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
        resolved = resolve_company_from_text(f"{report.ticker} {report.company} {report.title}")
        if resolved is None:
            logger.info("지원 기업 외 리포트 제외: %s", report.report_id)
            return

        report.ticker = resolved["ticker"]
        report.company = resolved["company"]
        report.report_type = normalize_report_type(report.report_type, report.title)
        self.reports.upsert_report(report, "discovered")
        if self.reports.insert_target_price_if_present(report):
            counts["target_rows"] += 1

        if not report.pdf_url:
            self.reports.update_report_status(report.report_id, "no_pdf_url")
            return

        duplicate = self.reports.find_by_pdf_url(report.pdf_url)
        if duplicate is not None:
            self.reports.update_report_status(
                report.report_id,
                "duplicate",
                file_path=duplicate.get("file_path", ""),
                error_message=f"동일 pdf_url: {duplicate['report_id']}",
            )
            counts["duplicate"] += 1
            return

        final_path = self._build_pdf_path(report)
        try:
            result = downloader.download_to_temp(report.pdf_url, final_path)
            hash_duplicate = self.reports.find_by_sha256(result.pdf_hash)
            if hash_duplicate is not None:
                Path(result.temp_path).unlink(missing_ok=True)
                self.reports.update_report_status(
                    report.report_id,
                    "duplicate",
                    file_path=hash_duplicate.get("file_path", ""),
                    error_message=f"동일 sha256: {hash_duplicate['report_id']}",
                )
                counts["duplicate"] += 1
                return

            downloader.commit(result.temp_path, final_path)
            stored_path = self._stored_path(final_path)
            self.reports.insert_report_file(report, result, stored_path)
            self.reports.update_report_status(report.report_id, "success", file_path=stored_path)
            counts["downloaded"] += 1
            logger.info("PDF 저장 완료: %s -> %s", report.report_id, stored_path)
        except Exception as exc:
            self.reports.update_report_status(
                report.report_id,
                "failed",
                error_message=str(exc),
            )
            counts["failed"] += 1
            logger.exception("PDF 처리 실패: report_id=%s error=%s", report.report_id, exc)

    def _collect_numeric_data(self, counts: dict[str, int]) -> None:
        if self.settings.include_price_data:
            collector = PriceDataCollector(self.settings)
            for company in SUPPORTED_COMPANIES:
                try:
                    rows = collector.collect_price_data(company["ticker"], company["company"])
                    counts["price_rows"] += self.numeric_data.upsert_price_rows(rows)
                except Exception as exc:
                    logger.warning("주가 데이터 수집 실패: %s - %s", company["ticker"], exc)

        if self.settings.include_macro_data:
            try:
                rows = MacroDataCollector(self.settings).collect_macro_data()
                counts["macro_rows"] += self.numeric_data.upsert_macro_rows(rows)
            except Exception as exc:
                logger.warning("매크로 데이터 수집 실패: %s", exc)

    def _limit_collection_scope(
        self,
        reports: list[ReportMetadata],
    ) -> list[ReportMetadata]:
        per_company_counts: dict[str, int] = {}
        selected: list[ReportMetadata] = []
        sorted_reports = sorted(
            reports,
            key=lambda report: parse_date(report.published_at) or date.min,
            reverse=True,
        )
        for report in sorted_reports:
            if not is_within_months(report.published_at, self.settings.months):
                continue
            company_key = report.ticker or report.company or report.report_id
            company_count = per_company_counts.get(company_key, 0)
            if company_count >= self.settings.max_reports_per_company:
                continue
            selected.append(report)
            per_company_counts[company_key] = company_count + 1
            if len(selected) >= self.settings.max_total_reports:
                break
        logger.info(
            "수집 범위 적용: 최근 %s개월, 기업당 최대 %s개, 전체 최대 %s개, 결과 %s개",
            self.settings.months,
            self.settings.max_reports_per_company,
            self.settings.max_total_reports,
            len(selected),
        )
        return selected

    def _build_pdf_path(self, report: ReportMetadata) -> Path:
        published = parse_date(report.published_at) or date.today()
        return (
            self.settings.pdf_root
            / report.source.lower()
            / f"{published.year:04d}"
            / f"{published.month:02d}"
            / f"{published.day:02d}"
            / f"{report.report_id}.pdf"
        )

    @staticmethod
    def _stored_path(final_path: Path) -> str:
        try:
            return str(final_path.relative_to(PROJECT_ROOT))
        except ValueError:
            return str(final_path.resolve())

    @staticmethod
    def _deduplicate_reports(reports: Iterable[ReportMetadata]) -> list[ReportMetadata]:
        unique: dict[str, ReportMetadata] = {}
        for report in reports:
            unique[report.report_id] = report
        return list(unique.values())
