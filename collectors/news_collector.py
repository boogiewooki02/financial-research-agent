from __future__ import annotations

import hashlib
import html
import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

from config.settings import SETTINGS, Settings
from crawler.http import create_ssl_context

logger = logging.getLogger(__name__)


class NewsCollector:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or SETTINGS

    def collect_news_data(
        self,
        ticker: str,
        company: str,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict]:
        if self.settings.news_data_provider != "naver":
            raise ValueError(f"unsupported news data provider: {self.settings.news_data_provider}")
        if not self.settings.naver_client_id or not self.settings.naver_client_secret:
            logger.warning("NAVER_CLIENT_ID/SECRET이 없어 뉴스 수집을 건너뜁니다.")
            return []
        return NaverNewsProvider(self.settings).collect(
            ticker,
            company,
            date_from,
            date_to,
        )


class NaverNewsProvider:
    source = "NAVER_NEWS"

    def __init__(self, settings: Settings):
        self.settings = settings

    def collect(
        self,
        ticker: str,
        company: str,
        date_from: str | None,
        date_to: str | None,
    ) -> list[dict]:
        headers = {
            "X-Naver-Client-Id": self.settings.naver_client_id,
            "X-Naver-Client-Secret": self.settings.naver_client_secret,
            "User-Agent": self.settings.user_agent,
        }
        params = {
            "query": company,
            "display": 30,
            "sort": "date",
        }
        with httpx.Client(
            headers=headers,
            timeout=self.settings.request_timeout_seconds,
            follow_redirects=True,
            verify=create_ssl_context(),
        ) as client:
            response = client.get(
                "https://openapi.naver.com/v1/search/news.json",
                params=params,
            )
            response.raise_for_status()

        rows: list[dict] = []
        for item in response.json().get("items", []):
            published_at = _normalize_pub_date(item.get("pubDate", ""))
            if not _in_range(published_at, date_from, date_to):
                continue
            original_url = item.get("originallink") or item.get("link") or ""
            title = _clean_html(item.get("title", ""))
            summary = _clean_html(item.get("description", ""))
            news_id = hashlib.sha256(
                f"{ticker}|{published_at}|{title}|{original_url}".encode("utf-8")
            ).hexdigest()[:24]
            rows.append(
                {
                    "news_id": news_id,
                    "ticker": ticker,
                    "company": company,
                    "title": title,
                    "summary": summary,
                    "published_at": published_at,
                    "original_url": original_url,
                    "source": self.source,
                    "provider": "naver",
                    "created_at": _utc_now(),
                }
            )
        return rows


def _clean_html(value: str) -> str:
    return html.unescape(value).replace("<b>", "").replace("</b>", "").strip()


def _normalize_pub_date(value: str) -> str:
    if not value:
        return ""
    parsed = parsedate_to_datetime(value)
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")


def _in_range(value: str, date_from: str | None, date_to: str | None) -> bool:
    if not value:
        return False
    day = value[:10]
    if date_from and day < date_from:
        return False
    if date_to and day > date_to:
        return False
    return True


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
