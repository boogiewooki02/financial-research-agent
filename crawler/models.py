from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(init=False)
class ReportMetadata:
    """크롤러에서 수집해 저장 파이프라인으로 전달하는 리포트 DTO."""

    report_id: str
    title: str = ""
    source: str = ""
    author_org: str = ""
    published_at: str = ""
    report_type: str = ""
    ticker: str = ""
    company: str = ""
    original_url: str = ""
    pdf_url: str | None = None
    target_price: float | None = None
    investment_opinion: str | None = None

    def __init__(
        self,
        report_id: str,
        title: str = "",
        source: str = "",
        author_org: str = "",
        published_at: str = "",
        report_type: str = "",
        ticker: str = "",
        company: str = "",
        original_url: str = "",
        pdf_url: str | None = None,
        target_price: float | None = None,
        investment_opinion: str | None = None,
        securities_firm: str | None = None,
        published_date: str | None = None,
        stock_code: str | None = None,
        company_name: str | None = None,
        source_url: str | None = None,
    ) -> None:
        self.report_id = report_id
        self.title = title
        self.source = source
        self.author_org = author_org if securities_firm is None else securities_firm
        self.published_at = published_at if published_date is None else published_date
        self.report_type = report_type
        self.ticker = ticker if stock_code is None else stock_code
        self.company = company if company_name is None else company_name
        self.original_url = original_url if source_url is None else source_url
        self.pdf_url = pdf_url
        self.target_price = target_price
        self.investment_opinion = investment_opinion

    @property
    def securities_firm(self) -> str:
        return self.author_org

    @securities_firm.setter
    def securities_firm(self, value: str) -> None:
        self.author_org = value

    @property
    def published_date(self) -> str:
        return self.published_at

    @published_date.setter
    def published_date(self, value: str) -> None:
        self.published_at = value

    @property
    def stock_code(self) -> str:
        return self.ticker

    @stock_code.setter
    def stock_code(self, value: str) -> None:
        self.ticker = value

    @property
    def company_name(self) -> str:
        return self.company

    @company_name.setter
    def company_name(self, value: str) -> None:
        self.company = value

    @property
    def source_url(self) -> str:
        return self.original_url

    @source_url.setter
    def source_url(self, value: str) -> None:
        self.original_url = value

    def as_record(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "ticker": self.ticker,
            "company": self.company,
            "title": self.title,
            "source": self.source,
            "author_org": self.author_org,
            "published_at": self.published_at,
            "report_type": self.report_type,
            "original_url": self.original_url,
            "pdf_url": self.pdf_url,
            "target_price": self.target_price,
            "investment_opinion": self.investment_opinion,
        }


@dataclass
class DownloadResult:
    """PDF 다운로드 단계가 파이프라인에 반환하는 결과 DTO."""

    temp_path: str
    pdf_hash: str
    file_size: int = 0
    content_type: str = ""
    is_valid_pdf: bool = True
