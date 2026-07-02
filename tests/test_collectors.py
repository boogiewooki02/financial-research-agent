from __future__ import annotations

import unittest

from collectors.disclosure_collector import DisclosureCollector, _normalize_disclosure_type
from collectors.macro_data_collector import (
    DEFAULT_ECOS_INDICATORS,
    EcosMacroProvider,
    MacroDataCollector,
    NaverMarketIndexProvider,
)
from collectors.news_collector import (
    NewsCollector,
    _clean_html,
    _extract_article_text,
    _normalize_pub_date,
)
from collectors.price_data_collector import NaverPriceProvider, PriceDataCollector
from config.settings import Settings


class PriceDataCollectorTest(unittest.TestCase):
    def test_mock_provider_returns_price_rows(self) -> None:
        rows = PriceDataCollector(Settings(price_data_provider="mock")).collect_price_data(
            "005930",
            "삼성전자",
            "2026-06-17",
            "2026-06-18",
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["ticker"], "005930")
        self.assertEqual(rows[0]["source"], "MOCK")

    def test_months_setting_defines_default_price_period(self) -> None:
        rows = PriceDataCollector(
            Settings(price_data_provider="mock", months=2)
        ).collect_price_data(
            "005930",
            "삼성전자",
            date_to="2026-06-18",
        )

        self.assertEqual(rows[0]["price_date"], "2026-04-18")
        self.assertEqual(rows[-1]["price_date"], "2026-06-18")

    def test_naver_price_provider_parses_daily_price_rows(self) -> None:
        html = """
        <table class="type2"><tr>
          <td><span>2026.06.18</span></td><td>76,000</td><td>상승</td>
          <td>75,000</td><td>76,500</td><td>74,800</td><td>12,345,678</td>
        </tr></table>
        """
        rows = NaverPriceProvider(Settings())._parse_page(html, "005930", "삼성전자")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["price_date"], "2026-06-18")
        self.assertEqual(rows[0]["close"], 76000)
        self.assertEqual(rows[0]["source"], "NAVER_FINANCE")


class MacroDataCollectorTest(unittest.TestCase):
    def test_mock_provider_returns_macro_rows(self) -> None:
        rows = MacroDataCollector(Settings(macro_data_provider="mock")).collect_macro_data(
            ["USD_KRW"],
            date_to="2026-06-18",
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["indicator_id"], "USD_KRW")
        self.assertEqual(rows[0]["source"], "MOCK")

    def test_naver_market_index_provider_parses_usd_krw(self) -> None:
        html = """
        <div class="market1"><div class="head_info">
          <span class="value">1,380.50</span>
        </div></div>
        """

        value = NaverMarketIndexProvider(Settings())._parse_usd_krw(html)

        self.assertEqual(value, 1380.5)

    def test_ecos_provider_converts_indicator_row(self) -> None:
        provider = EcosMacroProvider(Settings(macro_data_provider="ecos"))
        row = provider._to_macro_row(
            DEFAULT_ECOS_INDICATORS["BASE_RATE_KR"],
            {"TIME": "20260618", "DATA_VALUE": "2.50", "UNIT_NAME": "%"},
        )

        self.assertEqual(row["indicator_id"], "BASE_RATE_KR")
        self.assertEqual(row["date"], "2026-06-18")
        self.assertEqual(row["value"], 2.5)
        self.assertEqual(row["source"], "ECOS")


class NewsCollectorTest(unittest.TestCase):
    def test_skip_without_naver_api_keys(self) -> None:
        rows = NewsCollector(
            Settings(naver_client_id="", naver_client_secret="")
        ).collect_news_data("005930", "삼성전자")

        self.assertEqual(rows, [])

    def test_news_helpers_normalize_values(self) -> None:
        self.assertEqual(_clean_html("<b>삼성전자</b> 뉴스"), "삼성전자 뉴스")
        self.assertTrue(
            _normalize_pub_date("Thu, 18 Jun 2026 09:00:00 +0900").startswith(
                "2026-06-18T00:00:00"
            )
        )

    def test_extract_article_text_from_common_article_node(self) -> None:
        body = " ".join(["삼성전자가 반도체 투자 계획을 발표했다."] * 20)
        html = f"<html><body><article>{body}</article></body></html>"

        self.assertIn("반도체 투자", _extract_article_text(html))


class DisclosureCollectorTest(unittest.TestCase):
    def test_skip_without_dart_api_key(self) -> None:
        rows = DisclosureCollector(
            Settings(dart_api_key="")
        ).collect_disclosure_data("005930", "삼성전자")

        self.assertEqual(rows, [])

    def test_infer_disclosure_type_from_report_name(self) -> None:
        self.assertEqual(
            _normalize_disclosure_type("", "분기보고서 (2026.03)"),
            "regular_report",
        )
        self.assertEqual(
            _normalize_disclosure_type("", "기업설명회(IR) 개최"),
            "ir",
        )


if __name__ == "__main__":
    unittest.main()
