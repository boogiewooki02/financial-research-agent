from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import urllib.robotparser
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup, Tag

from crawler.config import SELECTORS, Settings
from crawler.http import create_ssl_context
from crawler.models import ReportMetadata

logger = logging.getLogger(__name__)


class RobotsTxtDeniedError(RuntimeError):
    pass


class KirsResearchCrawler:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def crawl(self) -> list[ReportMetadata]:
        async with httpx.AsyncClient(
            headers={"User-Agent": self.settings.user_agent},
            timeout=self.settings.request_timeout_seconds,
            follow_redirects=True,
            verify=create_ssl_context(),
        ) as client:
            await self._ensure_robots_allowed(client)
            reports: list[ReportMetadata] = []

            for page_number in range(1, self.settings.max_pages + 1):
                url = self._page_url(page_number)
                logger.info("목록 페이지 수집: %s", url)
                response = await client.get(url)
                response.raise_for_status()
                reports.extend(self.parse_list_html(response.text, url))
                if page_number < self.settings.max_pages:
                    await asyncio.sleep(self.settings.request_delay_seconds)

        return self._deduplicate_page_results(reports)

    def parse_list_html(self, html: str, page_url: str) -> list[ReportMetadata]:
        soup = BeautifulSoup(html, "html.parser")
        reports: list[ReportMetadata] = []

        for row in soup.select(SELECTORS["report_rows"]):
            try:
                report = self._parse_row(row, page_url)
                if report is not None:
                    reports.append(report)
            except Exception:
                logger.exception("리포트 행 파싱 실패")

        return reports

    def _parse_row(self, row: Tag, page_url: str) -> ReportMetadata | None:
        cells = row.select(SELECTORS["cells"])
        if len(cells) < 4:
            return None

        company_name, stock_code = self._parse_company(cells[0].get_text(" ", strip=True))
        title = cells[1].get_text(" ", strip=True)
        author_or_firm = cells[2].get_text(" ", strip=True)
        published_date = self._normalize_date(cells[3].get_text(" ", strip=True))

        pdf_link = row.select_one(SELECTORS["pdf_link"])
        pdf_url = ""
        if pdf_link is not None:
            raw_pdf_url = (
                pdf_link.get("href") or pdf_link.get("data-url") or ""
            ).strip()
            pdf_url = urljoin(page_url, raw_pdf_url)

        report_id = self._extract_report_id(row)
        if not report_id:
            identity = pdf_url or f"{page_url}|{stock_code}|{published_date}|{title}"
            report_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]

        if not any((title, company_name, pdf_url)):
            return None

        return ReportMetadata(
            report_id=f"kirs-{report_id}",
            title=title,
            securities_firm=author_or_firm,
            published_date=published_date,
            report_type=self.settings.report_type,
            stock_code=stock_code,
            company_name=company_name,
            source_url=page_url,
            pdf_url=pdf_url,
        )

    @staticmethod
    def _extract_report_id(row: Tag) -> str:
        id_source = row.select_one(SELECTORS["report_id_source"])
        onclick = id_source.get("onclick", "") if id_source else ""
        match = re.search(r"add_hit\(\s*(\d+)", onclick)
        if match:
            return match.group(1)

        pdf_link = row.select_one("a.pdf-download[data-no]")
        return pdf_link.get("data-no", "").strip() if pdf_link else ""

    @staticmethod
    def _parse_company(value: str) -> tuple[str, str]:
        match = re.match(r"^(.*?)\s*\(\s*(\d{6})\s*\)\s*$", value)
        if not match:
            return value.strip(), ""
        return match.group(1).strip(), match.group(2)

    @staticmethod
    def _normalize_date(value: str) -> str:
        for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%y-%m-%d", "%y.%m.%d"):
            try:
                return datetime.strptime(value, fmt).date().isoformat()
            except ValueError:
                continue
        return value

    def _page_url(self, page_number: int) -> str:
        parsed = urlparse(self.settings.research_url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query["page"] = str(page_number)
        return urlunparse(parsed._replace(query=urlencode(query)))

    async def _ensure_robots_allowed(self, client: httpx.AsyncClient) -> None:
        if not self.settings.respect_robots_txt:
            logger.warning(
                "robots.txt 검사를 비활성화했습니다. 사이트 운영 정책을 확인하세요."
            )
            return

        parsed = urlparse(self.settings.research_url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        response = await client.get(robots_url)
        response.raise_for_status()

        parser = urllib.robotparser.RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(response.text.splitlines())
        if not parser.can_fetch(self.settings.user_agent, self.settings.research_url):
            raise RobotsTxtDeniedError(
                f"robots.txt가 현재 User-Agent의 접근을 허용하지 않습니다: {robots_url}"
            )

    @staticmethod
    def _deduplicate_page_results(
        reports: list[ReportMetadata],
    ) -> list[ReportMetadata]:
        unique: dict[str, ReportMetadata] = {}
        for report in reports:
            unique[report.report_id] = report
        return list(unique.values())
