from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"

load_dotenv(ENV_FILE, override=False)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(*names: str, default: int) -> int:
    for name in names:
        value = os.getenv(name)
        if value is not None:
            return int(value)
    return default


def _env_float(*names: str, default: float) -> float:
    for name in names:
        value = os.getenv(name)
        if value is not None:
            return float(value)
    return default


@dataclass(frozen=True)
class Settings:
    source: str = os.getenv("CRAWLER_SOURCE", os.getenv("COLLECTION_SOURCE", "naver"))
    naver_research_url: str = os.getenv(
        "NAVER_RESEARCH_URL",
        "https://finance.naver.com/research/company_list.naver",
    )
    kirs_research_url: str = os.getenv(
        "KIRS_RESEARCH_URL",
        "https://www.kirs.or.kr/research/research22_1.html",
    )
    report_type: str = os.getenv("REPORT_TYPE", "company_report")
    user_agent: str = os.getenv(
        "CRAWLER_USER_AGENT",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36 InternalResearchCollector/1.0",
    )

    db_path: Path = Path(
        os.getenv("DATABASE_PATH", str(PROJECT_ROOT / "db" / "reports.db"))
    )
    pdf_root: Path = Path(
        os.getenv(
            "PDF_STORAGE_PATH",
            str(PROJECT_ROOT / "storage" / "raw_report_pdfs"),
        )
    )
    log_dir: Path = Path(os.getenv("LOG_DIR", str(PROJECT_ROOT / "logs")))

    request_timeout_seconds: float = _env_float(
        "REQUEST_TIMEOUT",
        "REQUEST_TIMEOUT_SECONDS",
        default=20,
    )
    request_delay_seconds: float = _env_float(
        "REQUEST_INTERVAL_SECONDS",
        "REQUEST_DELAY_SECONDS",
        default=1.5,
    )
    download_retries: int = _env_int("MAX_RETRIES", "DOWNLOAD_RETRIES", default=3)
    max_pages: int = _env_int("MAX_PAGES", default=3)
    months: int = _env_int("COLLECTION_MONTHS", default=1)
    max_reports_per_company: int = _env_int("MAX_REPORTS_PER_COMPANY", default=10)
    max_total_reports: int = _env_int("MAX_TOTAL_REPORTS", default=50)
    include_price_data: bool = _env_bool("INCLUDE_PRICE_DATA", False)
    include_macro_data: bool = _env_bool("INCLUDE_MACRO_DATA", False)
    include_news_data: bool = _env_bool("INCLUDE_NEWS_DATA", False)
    include_disclosure_data: bool = _env_bool("INCLUDE_DISCLOSURE_DATA", False)
    respect_robots_txt: bool = _env_bool("RESPECT_ROBOTS_TXT", True)

    schedule_hour: int = _env_int("CRAWLER_SCHEDULE_HOUR", "SCHEDULE_HOUR", default=7)
    schedule_minute: int = _env_int(
        "CRAWLER_SCHEDULE_MINUTE",
        "SCHEDULE_MINUTE",
        default=0,
    )
    schedule_timezone: str = os.getenv("SCHEDULE_TIMEZONE", "Asia/Seoul")

    price_data_provider: str = os.getenv("PRICE_DATA_PROVIDER", "naver")
    macro_data_provider: str = os.getenv("MACRO_DATA_PROVIDER", "naver")
    news_data_provider: str = os.getenv("NEWS_DATA_PROVIDER", "naver")
    disclosure_data_provider: str = os.getenv("DISCLOSURE_DATA_PROVIDER", "dart")
    naver_client_id: str = os.getenv("NAVER_CLIENT_ID", "")
    naver_client_secret: str = os.getenv("NAVER_CLIENT_SECRET", "")
    dart_api_key: str = os.getenv("DART_API_KEY", "")
    ecos_api_key: str = os.getenv("ECOS_API_KEY", "")
    kis_app_key: str = os.getenv("KIS_APP_KEY", "")
    kis_app_secret: str = os.getenv("KIS_APP_SECRET", "")

    def __post_init__(self) -> None:
        if self.source not in {"naver", "kirs", "all"}:
            raise ValueError("source must be one of: naver, kirs, all")
        if self.months < 1:
            raise ValueError("COLLECTION_MONTHS must be at least 1")
        if self.max_pages < 1:
            raise ValueError("MAX_PAGES must be at least 1")
        if self.max_reports_per_company < 1:
            raise ValueError("MAX_REPORTS_PER_COMPANY must be at least 1")
        if self.max_total_reports < 1:
            raise ValueError("MAX_TOTAL_REPORTS must be at least 1")
        if self.download_retries < 1:
            raise ValueError("MAX_RETRIES/DOWNLOAD_RETRIES must be at least 1")

    @property
    def research_url(self) -> str:
        return self.kirs_research_url


SETTINGS = Settings()
