from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

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
        if self.settings.macro_data_provider == "ecos":
            rows = EcosMacroProvider(self.settings).collect(
                indicators,
                date_from,
                date_to,
            )
            selected = indicators or list(DEFAULT_ECOS_INDICATORS) + ["USD_KRW"]
            if "USD_KRW" in selected:
                rows.extend(
                    NaverMarketIndexProvider(self.settings).collect(
                        ["USD_KRW"],
                        date_from,
                        date_to,
                    )
                )
            return rows
        raise ValueError(f"unsupported macro data provider: {self.settings.macro_data_provider}")


@dataclass(frozen=True)
class EcosIndicator:
    indicator_id: str
    indicator_name: str
    stat_code: str
    cycle: str
    item_code: str
    unit: str
    frequency: str
    country: str = "KR"


DEFAULT_ECOS_INDICATORS = {
    "BASE_RATE_KR": EcosIndicator(
        indicator_id="BASE_RATE_KR",
        indicator_name="한국 기준금리",
        stat_code="722Y001",
        cycle="D",
        item_code="0101000",
        unit="%",
        frequency="daily",
    ),
    "KTB_3Y_KR": EcosIndicator(
        indicator_id="KTB_3Y_KR",
        indicator_name="국고채 3년 금리",
        stat_code="817Y002",
        cycle="D",
        item_code="010200000",
        unit="%",
        frequency="daily",
    ),
    "KTB_10Y_KR": EcosIndicator(
        indicator_id="KTB_10Y_KR",
        indicator_name="국고채 10년 금리",
        stat_code="817Y002",
        cycle="D",
        item_code="010220000",
        unit="%",
        frequency="daily",
    ),
    "CPI_KR": EcosIndicator(
        indicator_id="CPI_KR",
        indicator_name="한국 소비자물가지수",
        stat_code="901Y009",
        cycle="M",
        item_code="0",
        unit="index",
        frequency="monthly",
    ),
}


class EcosMacroProvider:
    source = "ECOS"

    def __init__(self, settings: Settings):
        self.settings = settings

    def collect(
        self,
        indicators: list[str] | None,
        date_from: str | None,
        date_to: str | None,
    ) -> list[dict]:
        if not self.settings.ecos_api_key:
            logger.warning("ECOS_API_KEY가 없어 ECOS 매크로 수집을 건너뜁니다.")
            return []

        selected = indicators or list(DEFAULT_ECOS_INDICATORS)
        rows: list[dict] = []
        with httpx.Client(
            headers={"User-Agent": self.settings.user_agent},
            timeout=self.settings.request_timeout_seconds,
            follow_redirects=True,
            verify=create_ssl_context(),
        ) as client:
            for indicator_id in selected:
                indicator = DEFAULT_ECOS_INDICATORS.get(indicator_id)
                if indicator is None:
                    if indicator_id != "USD_KRW":
                        logger.warning("지원하지 않는 ECOS 지표입니다: %s", indicator_id)
                    continue
                try:
                    ecos_rows = self._fetch_indicator(client, indicator, date_from, date_to)
                    if ecos_rows:
                        rows.append(self._to_macro_row(indicator, ecos_rows[-1]))
                except Exception as exc:
                    logger.warning("ECOS 지표 수집 실패: %s - %s", indicator_id, exc)
        return rows

    def _fetch_indicator(
        self,
        client: httpx.Client,
        indicator: EcosIndicator,
        date_from: str | None,
        date_to: str | None,
    ) -> list[dict]:
        start, end = _ecos_date_range(indicator.cycle, date_from, date_to)
        url = (
            "https://ecos.bok.or.kr/api/StatisticSearch/"
            f"{self.settings.ecos_api_key}/json/kr/1/100/"
            f"{indicator.stat_code}/{indicator.cycle}/{start}/{end}/{indicator.item_code}"
        )
        response = client.get(url)
        response.raise_for_status()
        payload = response.json()
        result = payload.get("StatisticSearch")
        if not result:
            message = payload.get("RESULT", {}).get("MESSAGE", "응답 없음")
            raise RuntimeError(message)
        rows = result.get("row") or result.get("list") or []
        rows = sorted(rows, key=lambda row: row.get("TIME", ""))
        return rows

    def _to_macro_row(self, indicator: EcosIndicator, row: dict) -> dict:
        return {
            "indicator_id": indicator.indicator_id,
            "indicator_name": indicator.indicator_name,
            "date": _normalize_ecos_time(row.get("TIME", ""), indicator.cycle),
            "value": _parse_number(row.get("DATA_VALUE", "")),
            "unit": row.get("UNIT_NAME") or indicator.unit,
            "frequency": indicator.frequency,
            "country": indicator.country,
            "source": self.source,
            "created_at": _utc_now(),
        }


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


def _ecos_date_range(
    cycle: str,
    date_from: str | None,
    date_to: str | None,
) -> tuple[str, str]:
    end = _parse_iso_date(date_to) or date.today()
    if date_from:
        start = _parse_iso_date(date_from) or end
    elif cycle == "M":
        start = end - timedelta(days=400)
    else:
        start = end - timedelta(days=45)

    if cycle == "M":
        return start.strftime("%Y%m"), end.strftime("%Y%m")
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def _normalize_ecos_time(value: str, cycle: str) -> str:
    if not value:
        return ""
    if cycle == "M":
        return datetime.strptime(value, "%Y%m").date().replace(day=1).isoformat()
    return datetime.strptime(value, "%Y%m%d").date().isoformat()
