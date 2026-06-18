from __future__ import annotations

import logging
import re
from datetime import date, datetime, timezone

import httpx
from bs4 import BeautifulSoup

from config.settings import SETTINGS, Settings
from crawler.http import create_ssl_context

logger = logging.getLogger(__name__)


DEFAULT_INDICATORS = {
    "USD_KRW": {
        "indicator_name": "원/달러 환율",
        "value": 1380.5,
        "unit": "KRW",
        "frequency": "daily",
        "country": "KR",
    },
    "BASE_RATE_KR": {
        "indicator_name": "한국 기준금리",
        "value": 3.5,
        "unit": "%",
        "frequency": "monthly",
        "country": "KR",
    },
    "CPI_KR": {
        "indicator_name": "한국 소비자물가지수",
        "value": 114.2,
        "unit": "index",
        "frequency": "monthly",
        "country": "KR",
    },
}


class MacroDataCollector:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or SETTINGS

    def collect_macro_data(
        self,
        indicators: list[str] | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict]:
        if self.settings.macro_data_provider == "mock":
            return MockMacroProvider().collect(indicators, date_from, date_to)
        if self.settings.macro_data_provider == "naver":
            return NaverMarketIndexProvider(self.settings).collect(
                indicators,
                date_from,
                date_to,
            )
        raise ValueError(f"unsupported macro data provider: {self.settings.macro_data_provider}")


class NaverMarketIndexProvider:
    source = "NAVER_MARKETINDEX"
    supported_indicators = {"USD_KRW"}

    def __init__(self, settings: Settings):
        self.settings = settings

    def collect(
        self,
        indicators: list[str] | None,
        date_from: str | None,
        date_to: str | None,
    ) -> list[dict]:
        selected = indicators or ["USD_KRW"]
        unsupported = sorted(set(selected) - self.supported_indicators)
        if unsupported:
            logger.warning(
                "Naver 시장지표 provider는 현재 USD_KRW만 지원합니다: skipped=%s",
                ", ".join(unsupported),
            )

        rows: list[dict] = []
        if "USD_KRW" not in selected:
            return rows

        url = "https://finance.naver.com/marketindex/"
        with httpx.Client(
            headers={"User-Agent": self.settings.user_agent},
            timeout=self.settings.request_timeout_seconds,
            follow_redirects=True,
            verify=create_ssl_context(),
        ) as client:
            response = client.get(url)
            response.raise_for_status()

        value = self._parse_usd_krw(response.text)
        row_date = date_to or date_from or date.today().isoformat()
        return [
            {
                "indicator_id": "USD_KRW",
                "indicator_name": "원/달러 환율",
                "date": row_date,
                "value": value,
                "unit": "KRW",
                "frequency": "daily",
                "country": "KR",
                "source": self.source,
                "created_at": _utc_now(),
            }
        ]

    @staticmethod
    def _parse_usd_krw(html: str) -> float:
        soup = BeautifulSoup(html, "html.parser")
        exchange_block = soup.select_one("div.market1 div.head_info span.value")
        if exchange_block is not None:
            return _parse_number(exchange_block.get_text(" ", strip=True))

        text = soup.get_text(" ", strip=True)
        match = re.search(r"미국\s*USD.*?([0-9]{1,3}(?:,[0-9]{3})*(?:\.\d+)?)", text)
        if match:
            return _parse_number(match.group(1))
        raise ValueError("USD/KRW 값을 Naver 시장지표 페이지에서 찾지 못했습니다")


class MockMacroProvider:
    source = "MOCK"

    def collect(
        self,
        indicators: list[str] | None,
        date_from: str | None,
        date_to: str | None,
    ) -> list[dict]:
        selected = indicators or list(DEFAULT_INDICATORS)
        row_date = date_to or date_from or date.today().isoformat()
        rows: list[dict] = []
        for indicator_id in selected:
            metadata = DEFAULT_INDICATORS.get(indicator_id)
            if metadata is None:
                continue
            rows.append(
                {
                    "indicator_id": indicator_id,
                    "indicator_name": metadata["indicator_name"],
                    "date": row_date,
                    "value": metadata["value"],
                    "unit": metadata["unit"],
                    "frequency": metadata["frequency"],
                    "country": metadata["country"],
                    "source": self.source,
                    "created_at": _utc_now(),
                }
            )
        return rows


def collect_macro_data(
    indicators: list[str] | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    return MacroDataCollector().collect_macro_data(indicators, date_from, date_to)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_number(value: str) -> float:
    return float(value.replace(",", "").strip())
