from __future__ import annotations

import argparse
import logging
from dataclasses import replace
from logging.handlers import TimedRotatingFileHandler

from crawler.config import SETTINGS, Settings
from crawler.pipeline import CollectionPipeline
from crawler.scheduler import run_scheduler
from db.database import Database


SUPPORTED_SOURCES = {"naver", "kirs", "all"}


def configure_logging(settings: Settings) -> None:
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = TimedRotatingFileHandler(
        settings.log_dir / "crawler.log",
        when="midnight",
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    logging.basicConfig(
        level=logging.INFO,
        handlers=[console_handler, file_handler],
        force=True,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Agent B financial data collection pipeline"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run-once", action="store_true", help="수집 작업을 한 번 실행")
    mode.add_argument("--schedule", action="store_true", help="일일 스케줄러 실행")
    mode.add_argument("--init-db", action="store_true", help="SQLite 스키마 초기화")
    parser.add_argument(
        "--source",
        choices=sorted(SUPPORTED_SOURCES),
        default=None,
        help="수집원 선택",
    )
    parser.add_argument(
        "--months",
        type=_positive_int,
        default=None,
        help="오늘 기준 최근 N개월 리포트 및 주가 데이터 수집",
    )
    parser.add_argument(
        "--max-reports-per-company",
        type=_positive_int,
        default=None,
        help="기업당 최대 수집 리포트 수",
    )
    parser.add_argument(
        "--max-total-reports",
        type=_positive_int,
        default=None,
        help="전체 실행 기준 최대 수집 리포트 수",
    )
    parser.add_argument(
        "--max-pages",
        type=_positive_int,
        default=None,
        help="기업별 최대 페이지 수",
    )
    parser.add_argument(
        "--include-price-data",
        action="store_true",
        help="설정된 provider 기준 주가 데이터도 수집",
    )
    parser.add_argument(
        "--include-macro-data",
        action="store_true",
        help="설정된 provider 기준 매크로 데이터도 수집",
    )
    parser.add_argument(
        "--include-news-data",
        action="store_true",
        help="설정된 provider 기준 뉴스 데이터도 수집",
    )
    parser.add_argument(
        "--include-disclosure-data",
        action="store_true",
        help="설정된 provider 기준 공시 데이터도 수집",
    )
    return parser.parse_args()


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def apply_cli_overrides(settings: Settings, args: argparse.Namespace) -> Settings:
    overrides = {}
    if args.source is not None:
        overrides["source"] = args.source
    if args.months is not None:
        overrides["months"] = args.months
    if args.max_reports_per_company is not None:
        overrides["max_reports_per_company"] = args.max_reports_per_company
    if args.max_total_reports is not None:
        overrides["max_total_reports"] = args.max_total_reports
    if args.max_pages is not None:
        overrides["max_pages"] = args.max_pages
    if args.include_price_data:
        overrides["include_price_data"] = True
    if args.include_macro_data:
        overrides["include_macro_data"] = True
    if args.include_news_data:
        overrides["include_news_data"] = True
    if args.include_disclosure_data:
        overrides["include_disclosure_data"] = True
    return replace(settings, **overrides) if overrides else settings


def main() -> int:
    args = parse_args()
    settings = apply_cli_overrides(SETTINGS, args)
    configure_logging(settings)
    logger = logging.getLogger(__name__)

    if settings.source not in SUPPORTED_SOURCES:
        logger.error(
            "지원하지 않는 수집원입니다: %s (현재 지원: %s)",
            settings.source,
            ", ".join(sorted(SUPPORTED_SOURCES)),
        )
        return 2

    if args.init_db:
        Database(settings.db_path).initialize()
        logger.info("DB 초기화 완료: %s", settings.db_path)
        return 0
    if args.run_once:
        try:
            CollectionPipeline(settings).run()
            return 0
        except Exception:
            # The pipeline already persists the failed run and logs the traceback.
            return 1

    run_scheduler(settings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
