from __future__ import annotations

import hashlib
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import httpx

from config.report_type_codes import normalize_report_type
from config.supported_companies import resolve_company_from_text
from crawler.base_crawler import generate_report_id
from crawler.config import Settings
from crawler.kirs_research_crawler import KirsResearchCrawler
from crawler.models import ReportMetadata
from crawler.pdf_downloader import PdfDownloadError, PdfDownloader, is_pdf_content
from crawler.pipeline import CollectionPipeline
from db.database import Database
from db.repositories import ReportRepository


SAMPLE_HTML = """
<table class="board_list_table04">
  <tbody>
    <tr>
      <td class="txt-left growup txtl">삼성전자 (005930)</td>
      <td class="txt-left text mobile_display">
        <p class="inline_block new_icon"></p>테스트 리포트
      </td>
      <td class="growup txtl">한국IR협의회</td>
      <td class="growup">2026-06-14</td>
      <td class="growup">
        <a href="https://w4.kirs.or.kr/download/research/report.pdf">
          <img src="/images/common/icon_pdf.jpg" onclick="add_hit(12345)">
        </a>
      </td>
    </tr>
  </tbody>
</table>
"""


class CrawlerParserTest(unittest.TestCase):
    def test_parse_report_row(self) -> None:
        crawler = KirsResearchCrawler(Settings())
        reports = crawler.parse_list_html(
            SAMPLE_HTML,
            "https://www.kirs.or.kr/research/research22_1.html?page=1",
        )

        self.assertEqual(len(reports), 1)
        report = reports[0]
        self.assertTrue(report.report_id.startswith("KIRS_005930_20260614_"))
        self.assertEqual(report.stock_code, "005930")
        self.assertEqual(report.company_name, "삼성전자")
        self.assertEqual(report.title, "테스트 리포트")
        self.assertEqual(report.securities_firm, "한국IR협의회")
        self.assertEqual(report.published_date, "2026-06-14")
        self.assertEqual(report.source, "KIRS")
        self.assertEqual(report.report_type, "company_report")
        self.assertEqual(
            report.pdf_url,
            "https://w4.kirs.or.kr/download/research/report.pdf",
        )

    def test_parse_ai_report_data_url(self) -> None:
        html = """
        <table class="board_list_table04"><tbody><tr>
          <td>쓰리빌리언 (394800)</td>
          <td>AI 기업분석</td>
          <td>한국IR협의회</td>
          <td>2026-06-13</td>
          <td><a class="pdf-download" data-no="504"
            data-url="https://api.kirs.or.kr/aireport/504/report.pdf"></a></td>
        </tr></tbody></table>
        """
        crawler = KirsResearchCrawler(Settings(report_type="KIRS_AI"))
        report = crawler.parse_list_html(
            html,
            "https://www.kirs.or.kr/research/ai_report.html?page=1",
        )[0]

        self.assertTrue(report.report_id.startswith("KIRS_394800_20260613_"))
        self.assertEqual(report.report_type, "ai_company_report")
        self.assertEqual(report.stock_code, "394800")
        self.assertEqual(
            report.pdf_url,
            "https://api.kirs.or.kr/aireport/504/report.pdf",
        )


class DatabaseTest(unittest.TestCase):
    def test_initialize_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "reports.db")
            database.initialize()
            with database.connect() as connection:
                tables = {
                    row["name"]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }

        self.assertIn("report_metadata", tables)
        self.assertIn("report_files", tables)
        self.assertIn("target_price_data", tables)
        self.assertIn("price_data", tables)
        self.assertIn("macro_data", tables)
        self.assertIn("news_metadata", tables)
        self.assertIn("disclosure_metadata", tables)
        self.assertIn("crawler_runs", tables)


class PdfDownloaderTest(unittest.TestCase):
    def test_download_valid_pdf_to_temp(self) -> None:
        body = b"%PDF-1.7\nmock pdf"
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"Content-Type": "application/pdf"},
                content=body,
            )
        )
        downloader = PdfDownloader(Settings(request_delay_seconds=0))
        downloader.client.close()
        downloader.client = httpx.Client(transport=transport)

        with tempfile.TemporaryDirectory() as directory:
            final_path = Path(directory) / "report.pdf"
            result = downloader.download_to_temp(
                "https://example.com/report.pdf",
                final_path,
            )
            self.assertEqual(Path(result.temp_path).read_bytes(), body)
            self.assertEqual(result.pdf_hash, hashlib.sha256(body).hexdigest())

        downloader.close()

    def test_reject_non_pdf_content_type(self) -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"Content-Type": "text/html"},
                content=b"<html>error</html>",
            )
        )
        downloader = PdfDownloader(
            Settings(request_delay_seconds=0, download_retries=1)
        )
        downloader.client.close()
        downloader.client = httpx.Client(transport=transport)

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(PdfDownloadError):
                downloader.download_to_temp(
                    "https://example.com/report.pdf",
                    Path(directory) / "report.pdf",
                )

        downloader.close()


class CompanyResolverTest(unittest.TestCase):
    def test_resolve_company_from_alias(self) -> None:
        resolved = resolve_company_from_text("삼전 신규 리포트")
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved["ticker"], "005930")
        self.assertEqual(resolved["match_status"], "alias")


class ReportTypeTest(unittest.TestCase):
    def test_normalize_report_type(self) -> None:
        self.assertEqual(normalize_report_type("기업분석"), "company_report")
        self.assertEqual(normalize_report_type("산업분석"), "industry_report")
        self.assertEqual(normalize_report_type("이슈분석"), "issue_comment")
        self.assertEqual(normalize_report_type("기술분석"), "technical_report")
        self.assertEqual(normalize_report_type("AI기업분석"), "ai_company_report")
        self.assertEqual(normalize_report_type(None), "unknown")


class ReportIdTest(unittest.TestCase):
    def test_generate_report_id_is_stable(self) -> None:
        first = generate_report_id(
            "NAVER",
            "005930",
            "2026-06-18",
            "삼성전자 기업분석",
            "https://example.com/report.pdf",
        )
        second = generate_report_id(
            "NAVER",
            "005930",
            "2026-06-18",
            "삼성전자 기업분석",
            "https://example.com/report.pdf",
        )
        self.assertEqual(first, second)
        self.assertTrue(first.startswith("NAVER_005930_20260618_"))


class RepositoryTest(unittest.TestCase):
    def test_duplicate_check_and_target_price_condition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "reports.db")
            database.initialize()
            repository = ReportRepository(database)
            report = ReportMetadata(
                report_id="NAVER_005930_20260618_aaaaaaaa",
                ticker="005930",
                company="삼성전자",
                title="삼성전자 기업분석",
                source="NAVER",
                author_org="테스트증권",
                published_at="2026-06-18",
                report_type="company_report",
                original_url="https://example.com/detail",
                pdf_url="https://example.com/report.pdf",
                target_price=95000,
                investment_opinion="매수",
            )
            repository.upsert_report(report)
            self.assertIsNone(repository.find_by_pdf_url(report.pdf_url))
            self.assertTrue(repository.insert_target_price_if_present(report))
            with database.connect() as connection:
                count = connection.execute(
                    "SELECT COUNT(*) AS count FROM target_price_data"
                ).fetchone()["count"]
            self.assertEqual(count, 1)

            result = type(
                "Result",
                (),
                {
                    "pdf_hash": "abc",
                    "file_size": 10,
                    "content_type": "application/pdf",
                    "is_valid_pdf": True,
                },
            )()
            repository.insert_report_file(report, result, "storage/report.pdf")
            self.assertIsNotNone(repository.find_by_pdf_url(report.pdf_url))
            self.assertIsNotNone(repository.find_by_sha256("abc"))

    def test_news_and_disclosure_rows_are_saved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "reports.db")
            database.initialize()
            from db.repositories import NumericDataRepository

            repository = NumericDataRepository(database)
            news_count = repository.upsert_news_rows(
                [
                    {
                        "news_id": "news-1",
                        "ticker": "005930",
                        "company": "삼성전자",
                        "title": "뉴스",
                        "summary": "요약",
                        "published_at": "2026-06-18T00:00:00+00:00",
                        "original_url": "https://example.com/news",
                        "source": "NAVER_NEWS",
                        "provider": "naver",
                        "created_at": "2026-06-18T00:00:00+00:00",
                    }
                ]
            )
            disclosure_count = repository.upsert_disclosure_rows(
                [
                    {
                        "disclosure_id": "disc-1",
                        "ticker": "005930",
                        "company": "삼성전자",
                        "corp_code": "00126380",
                        "report_name": "공시",
                        "disclosure_type": "A",
                        "disclosed_at": "2026-06-18",
                        "receipt_no": "20260618000001",
                        "original_url": "https://dart.fss.or.kr",
                        "source": "OPENDART",
                        "created_at": "2026-06-18T00:00:00+00:00",
                    }
                ]
            )

            self.assertEqual(news_count, 1)
            self.assertEqual(disclosure_count, 1)


class PdfUtilsTest(unittest.TestCase):
    def test_pdf_signature_validation(self) -> None:
        self.assertTrue(is_pdf_content("text/plain", b"%PDF-1.7"))
        self.assertTrue(is_pdf_content("application/pdf", b"not-pdf"))
        self.assertFalse(is_pdf_content("text/html", b"<html>"))


class CollectionScopeTest(unittest.TestCase):
    def test_limit_collection_scope_by_month_company_and_total(self) -> None:
        today = date.today()
        recent = (today - timedelta(days=5)).isoformat()
        old = (today - timedelta(days=70)).isoformat()
        reports = [
            ReportMetadata(
                report_id=f"recent-a-{index}",
                published_date=recent,
                stock_code="005930",
            )
            for index in range(3)
        ]
        reports.extend(
            [
                ReportMetadata(
                    report_id="recent-b-1",
                    published_date=recent,
                    stock_code="035420",
                ),
                ReportMetadata(
                    report_id="recent-b-2",
                    published_date=recent,
                    stock_code="035420",
                ),
                ReportMetadata(
                    report_id="old-c-1",
                    published_date=old,
                    stock_code="000660",
                ),
            ]
        )
        pipeline = CollectionPipeline(
            Settings(
                db_path=Path(":memory:"),
                months=1,
                max_reports_per_company=2,
                max_total_reports=3,
            )
        )

        scoped = pipeline._limit_collection_scope(reports)

        self.assertEqual(
            [report.report_id for report in scoped],
            ["recent-a-0", "recent-a-1", "recent-b-1"],
        )

    def test_unmatched_report_is_not_saved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pipeline = CollectionPipeline(
                Settings(
                    db_path=Path(directory) / "reports.db",
                    request_delay_seconds=0,
                    download_retries=1,
                )
            )
            pipeline.database.initialize()
            downloader = PdfDownloader(Settings(request_delay_seconds=0))
            try:
                pipeline._process_one(
                    ReportMetadata(
                        report_id="KIRS_478560_20260618_aaaaaaaa",
                        ticker="478560",
                        company="블랙야크아이앤씨",
                        title="소방사업 인수로 한층 넓어진 성장스토리",
                        source="KIRS",
                        published_at="2026-06-18",
                    ),
                    downloader,
                    {"target_rows": 0, "duplicate": 0, "downloaded": 0, "failed": 0},
                )
            finally:
                downloader.close()

            self.assertIsNone(
                pipeline.database.get_report("KIRS_478560_20260618_aaaaaaaa")
            )


if __name__ == "__main__":
    unittest.main()
