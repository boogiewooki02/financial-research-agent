from __future__ import annotations

from typing import Any


SUPPORTED_COMPANIES: list[dict[str, Any]] = [
    {
        "ticker": "005930",
        "company": "삼성전자",
        "sector": "반도체",
        "aliases": ["삼성전자", "삼전", "Samsung Electronics"],
    },
    {
        "ticker": "000660",
        "company": "SK하이닉스",
        "sector": "반도체",
        "aliases": ["SK하이닉스", "하이닉스", "Hynix"],
    },
    {
        "ticker": "005380",
        "company": "현대차",
        "sector": "자동차",
        "aliases": ["현대차", "현대자동차"],
    },
    {
        "ticker": "035420",
        "company": "NAVER",
        "sector": "플랫폼",
        "aliases": ["NAVER", "네이버"],
    },
    {
        "ticker": "003230",
        "company": "삼양식품",
        "sector": "음식료",
        "aliases": ["삼양식품"],
    },
    {
        "ticker": "352820",
        "company": "HYBE",
        "sector": "엔터테인먼트",
        "aliases": ["HYBE", "하이브"],
    },
    {
        "ticker": "373220",
        "company": "LG에너지솔루션",
        "sector": "2차전지",
        "aliases": ["LG에너지솔루션", "LG엔솔", "LG Energy Solution"],
    },
]


def resolve_company_from_text(text: str) -> dict[str, str] | None:
    normalized_text = text.casefold()
    for company in SUPPORTED_COMPANIES:
        if company["ticker"] in text:
            return _match_result(company, "ticker", company["ticker"])
        for alias in company["aliases"]:
            if alias.casefold() in normalized_text:
                return _match_result(company, "alias", alias)
    return None


def _match_result(
    company: dict[str, Any],
    match_status: str,
    matched_alias: str,
) -> dict[str, str]:
    return {
        "ticker": company["ticker"],
        "company": company["company"],
        "sector": company["sector"],
        "match_status": match_status,
        "matched_alias": matched_alias,
    }
