from __future__ import annotations

import logging
import math
import time
from datetime import date, datetime, timedelta, timezone
from itertools import count
from statistics import pstdev

import httpx
from bs4 import BeautifulSoup

from config.settings import SETTINGS, Settings
from crawler.base_crawler import subtract_months
from crawler.http import create_ssl_context

logger = logging.getLogger(__name__)


class PriceDataCollector:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or SETTINGS

    def collect_price_data(
        self,
        ticker: str,
        company: str,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict]:
        end = _parse_date(date_to) or date.today()
        start = _parse_date(date_from) or subtract_months(end, self.settings.months)
        resolved_date_from = start.isoformat()
        resolved_date_to = end.isoformat()
        if self.settings.price_data_provider == "mock":
            return MockPriceProvider().collect(
                ticker,
                company,
                resolved_date_from,
                resolved_date_to,
            )
        if self.settings.price_data_provider == "naver":
            return NaverPriceProvider(self.settings).collect(
                ticker,
                company,
                resolved_date_from,
                resolved_date_to,
            )
        raise ValueError(f"unsupported price data provider: {self.settings.price_data_provider}")


class NaverPriceProvider:
    source = "NAVER_FINANCE"

    def __init__(self, settings: Settings):
        self.settings = settings

    def collect(
        self,
        ticker: str,
        company: str,
        date_from: str | None,
        date_to: str | None,
    ) -> list[dict]:
        end = _parse_date(date_to) or date.today()
        start = _parse_date(date_from) or end - timedelta(days=45)
        rows: list[dict] = []
        with httpx.Client(
            headers={"User-Agent": self.settings.user_agent},
            timeout=self.settings.request_timeout_seconds,
            follow_redirects=True,
            verify=create_ssl_context(),
        ) as client:
            for page in count(1):
                url = (
                    "https://finance.naver.com/item/sise_day.naver"
                    f"?code={ticker}&page={page}"
                )
                response = client.get(url)
                response.raise_for_status()
                parsed_rows = self._parse_page(response.text, ticker, company)
                if not parsed_rows:
                    break
                rows.extend(
                    row
                    for row in parsed_rows
                    if start <= _parse_date(row["price_date"]) <= end
                )
                if min(_parse_date(row["price_date"]) for row in parsed_rows) <= start:
                    break
                time.sleep(self.settings.request_delay_seconds)

        unique = {row["price_date"]: row for row in rows}
        ordered = [unique[key] for key in sorted(unique)]
        self._attach_volatility(ordered)
        return ordered

    def _parse_page(self, html: str, ticker: str, company: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        rows: list[dict] = []
        for tr in soup.select("table.type2 tr"):
            cells = [td.get_text(" ", strip=True) for td in tr.select("td")]
            if len(cells) < 7:
                continue
            price_date = _parse_date(cells[0])
            if price_date is None:
                continue
            rows.append(
                {
                    "ticker": ticker,
                    "company": company,
                    "price_date": price_date.isoformat(),
                    "open": _parse_number(cells[3]),
                    "high": _parse_number(cells[4]),
                    "low": _parse_number(cells[5]),
                    "close": _parse_number(cells[1]),
                    "volume": int(_parse_number(cells[6]) or 0),
                    "market_cap": None,
                    "volatility_30d": None,
                    "source": self.source,
                    "created_at": _utc_now(),
                }
            )
        if not rows:
            logger.warning("NAVER 주가 페이지 구조 확인 필요: rows=0")
        return rows

    @staticmethod
    def _attach_volatility(rows: list[dict]) -> None:
        closes = [row["close"] for row in rows if row["close"]]
        if len(closes) < 2:
            return
        returns = [
            (closes[index] / closes[index - 1]) - 1
            for index in range(1, len(closes))
            if closes[index - 1]
        ]
        if not returns:
            return
        volatility = pstdev(returns) * math.sqrt(252)
        for row in rows:
            row["volatility_30d"] = volatility


class MockPriceProvider:
    source = "MOCK"

    def collect(
        self,
        ticker: str,
        company: str,
        date_from: str | None,
        date_to: str | None,
    ) -> list[dict]:
        end = _parse_date(date_to) or date.today()
        start = _parse_date(date_from) or end - timedelta(days=4)
        rows: list[dict] = []
        current = start
        seed = int(ticker[-3:] or "100")
        while current <= end:
            base = 50000 + seed * 10 + len(rows) * 100
            rows.append(
                {
                    "ticker": ticker,
                    "company": company,
                    "price_date": current.isoformat(),
                    "open": float(base),
                    "high": float(base + 500),
                    "low": float(base - 400),
                    "close": float(base + 100),
                    "volume": 1_000_000 + seed * 100 + len(rows),
                    "market_cap": None,
                    "volatility_30d": None,
                    "source": self.source,
                    "created_at": _utc_now(),
                }
            )
            current += timedelta(days=1)
        return rows


def collect_price_data(
    ticker: str,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    return PriceDataCollector().collect_price_data(ticker, "", date_from, date_to)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _parse_number(value: str) -> float | None:
    cleaned = value.replace(",", "").strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
