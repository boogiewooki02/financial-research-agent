from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

import httpx

from crawler.config import Settings
from crawler.kirs_research_crawler import KirsResearchCrawler
from crawler.pdf_downloader import PdfDownloadError, PdfDownloader
from db.database import Database


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
        self.assertEqual(report.report_id, "kirs-12345")
        self.assertEqual(report.stock_code, "005930")
        self.assertEqual(report.company_name, "삼성전자")
        self.assertEqual(report.title, "테스트 리포트")
        self.assertEqual(report.securities_firm, "한국IR협의회")
        self.assertEqual(report.published_date, "2026-06-14")
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

        self.assertEqual(report.report_id, "kirs-504")
        self.assertEqual(report.report_type, "KIRS_AI")
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

        self.assertIn("reports", tables)
        self.assertIn("collection_runs", tables)


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


if __name__ == "__main__":
    unittest.main()
