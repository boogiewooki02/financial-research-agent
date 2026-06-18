from __future__ import annotations

import logging
import re
import time
from datetime import date
from urllib.parse import urlencode, urljoin

import httpx
from bs4 import BeautifulSoup, Tag

from config.report_type_codes import normalize_report_type
from crawler.base_crawler import (
    generate_report_id,
    is_within_months,
    normalize_date,
)
from crawler.http import create_ssl_context
from crawler.models import ReportMetadata
from config.settings import Settings

logger = logging.getLogger(__name__)


NAVER_SELECTORS = {
    "report_rows": "table.type_1 tr, table.type_1 tbody tr",
    "cells": "td",
    "detail_link": "a[href]",
    "pdf_link": "a[href$='.pdf'], a[href*='.pdf?'], a[href*='download']",
}


class NaverResearchCrawler:
    def __init__(self, settings: Settings):
        self.settings = settings

    def fetch_reports_for_company(
        self,
        ticker: str,
        company: str,
        months: int = 6,
        max_pages: int = 3,
    ) -> list[dict]:
        reports: list[ReportMetadata] = []
        try:
            with httpx.Client(
                headers={"User-Agent": self.settings.user_agent},
                timeout=self.settings.request_timeout_seconds,
                follow_redirects=True,
                verify=create_ssl_context(),
            ) as client:
                for page in range(1, max_pages + 1):
                    url = self._page_url(company, page)
                    response = client.get(url)
                    response.raise_for_status()
                    page_reports = self.parse_list_html(
                        response.text,
                        url,
                        ticker,
                        company,
                        months,
                    )
                    logger.info(
                        "NAVER 기업별 리포트 발견: %s(%s) page=%s count=%s",
                        company,
                        ticker,
                        page,
                        len(page_reports),
                    )
                    reports.extend(page_reports)
                    time.sleep(self.settings.request_delay_seconds)
        except Exception as exc:
            logger.warning("NAVER 기업 수집 실패: %s(%s) - %s", company, ticker, exc)
        return [report.as_record() for report in self._deduplicate(reports)]

    def parse_list_html(
        self,
        html: str,
        page_url: str,
        ticker: str,
        company: str,
        months: int,
    ) -> list[ReportMetadata]:
        soup = BeautifulSoup(html, "html.parser")
        reports: list[ReportMetadata] = []
        rows = soup.select(NAVER_SELECTORS["report_rows"])
        if not rows:
            logger.warning("NAVER 리포트 목록 selector 결과 없음: %s", page_url)

        for row in rows:
            report = self._parse_row(row, page_url, ticker, company, months)
            if report is not None:
                reports.append(report)
        return reports

    def _parse_row(
        self,
        row: Tag,
        page_url: str,
        ticker: str,
        company: str,
        months: int,
    ) -> ReportMetadata | None:
        cells = [cell.get_text(" ", strip=True) for cell in row.select(NAVER_SELECTORS["cells"])]
        if len(cells) < 2:
            return None

        joined = " ".join(cells)
        if company.casefold() not in joined.casefold() and ticker not in joined:
            return None

        title_link = row.select_one(NAVER_SELECTORS["detail_link"])
        title = title_link.get_text(" ", strip=True) if title_link else cells[0]
        if not title:
            return None

        published_at = self._extract_date(cells)
        if not is_within_months(published_at, months):
            return None

        author_org = self._extract_author(cells)
        original_url = urljoin(page_url, title_link.get("href", "")) if title_link else page_url
        pdf_link = row.select_one(NAVER_SELECTORS["pdf_link"])
        pdf_url = urljoin(page_url, pdf_link.get("href", "")) if pdf_link else None
        target_price = self._extract_target_price(cells)
        investment_opinion = self._extract_opinion(cells)
        report_type = normalize_report_type(None, title)
        report_id = generate_report_id(
            "NAVER",
            ticker,
            published_at,
            title,
            pdf_url,
            original_url,
        )
        return ReportMetadata(
            report_id=report_id,
            source="NAVER",
            ticker=ticker,
            company=company,
            title=title,
            author_org=author_org,
            published_at=published_at,
            report_type=report_type,
            original_url=original_url,
            pdf_url=pdf_url,
            target_price=target_price,
            investment_opinion=investment_opinion,
        )

    def _page_url(self, company: str, page: int) -> str:
        query = urlencode({"keyword": company, "page": page})
        separator = "&" if "?" in self.settings.naver_research_url else "?"
        return f"{self.settings.naver_research_url}{separator}{query}"

    @staticmethod
    def _extract_date(cells: list[str]) -> str:
        for cell in reversed(cells):
            match = re.search(r"\d{4}[-.]\d{2}[-.]\d{2}|\d{2}[-.]\d{2}[-.]\d{2}", cell)
            if match:
                return normalize_date(match.group(0))
        return date.today().isoformat()

    @staticmethod
    def _extract_author(cells: list[str]) -> str:
        for cell in cells:
            if any(keyword in cell for keyword in ("증권", "투자", "리서치", "IR")):
                return cell
        return ""

    @staticmethod
    def _extract_target_price(cells: list[str]) -> float | None:
        for cell in cells:
            if not any(keyword in cell for keyword in ("목표", "TP", "Target")):
                continue
            match = re.search(r"([0-9][0-9,]+(?:\.\d+)?)", cell)
            if match:
                return float(match.group(1).replace(",", ""))
        return None

    @staticmethod
    def _extract_opinion(cells: list[str]) -> str | None:
        opinions = ("매수", "중립", "보유", "비중확대", "비중축소", "Buy", "Hold", "Sell")
        for cell in cells:
            for opinion in opinions:
                if opinion.casefold() in cell.casefold():
                    return opinion
        return None

    @staticmethod
    def _deduplicate(reports: list[ReportMetadata]) -> list[ReportMetadata]:
        unique: dict[str, ReportMetadata] = {}
        for report in reports:
            unique[report.report_id] = report
        return list(unique.values())
