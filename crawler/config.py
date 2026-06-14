from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"

# Local .env values are defaults. Shell, container, and CI environment
# variables keep precedence when they are already defined.
load_dotenv(ENV_FILE, override=False)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    research_url: str = os.getenv(
        "KIRS_RESEARCH_URL",
        "https://www.kirs.or.kr/research/research22_1.html",
    )
    report_type: str = os.getenv("REPORT_TYPE", "KIRS_RESEARCH")
    user_agent: str = os.getenv(
        "CRAWLER_USER_AGENT",
        "InternalResearchCollector/1.0 (+contact: admin@example.com)",
    )
    db_path: Path = Path(
        os.getenv("DATABASE_PATH", str(PROJECT_ROOT / "db" / "reports.db"))
    )
    pdf_root: Path = Path(
        os.getenv("PDF_STORAGE_PATH", str(PROJECT_ROOT / "storage" / "raw_pdfs"))
    )
    log_dir: Path = Path(os.getenv("LOG_DIR", str(PROJECT_ROOT / "logs")))
    request_timeout_seconds: float = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))
    request_delay_seconds: float = float(os.getenv("REQUEST_DELAY_SECONDS", "1.5"))
    download_retries: int = int(os.getenv("DOWNLOAD_RETRIES", "3"))
    max_pages: int = int(os.getenv("MAX_PAGES", "1"))
    respect_robots_txt: bool = _env_bool("RESPECT_ROBOTS_TXT", True)
    schedule_hour: int = int(os.getenv("SCHEDULE_HOUR", "7"))
    schedule_minute: int = int(os.getenv("SCHEDULE_MINUTE", "0"))
    schedule_timezone: str = os.getenv("SCHEDULE_TIMEZONE", "Asia/Seoul")


SETTINGS = Settings()

# Keep selectors centralized so KIRS markup changes can be handled without
# touching collection or persistence logic.
SELECTORS = {
    "report_rows": "table.board_list_table04 tbody tr",
    "cells": "td",
    "pdf_link": "a[href*='/download/'][href$='.pdf'], a.pdf-download[data-url]",
    "report_id_source": "img[onclick*='add_hit']",
}
