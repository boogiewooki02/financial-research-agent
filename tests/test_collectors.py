from __future__ import annotations

import unittest

from collectors.macro_data_collector import MacroDataCollector, NaverMarketIndexProvider
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


if __name__ == "__main__":
    unittest.main()
