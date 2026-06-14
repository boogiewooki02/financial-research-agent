from __future__ import annotations

import argparse
import logging
from logging.handlers import TimedRotatingFileHandler

from crawler.config import SETTINGS, Settings
from crawler.pipeline import CollectionPipeline
from crawler.scheduler import run_scheduler
from db.database import Database


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="KIRS research report PDF collector"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run-once", action="store_true", help="수집 작업을 한 번 실행")
    mode.add_argument("--schedule", action="store_true", help="일일 스케줄러 실행")
    mode.add_argument("--init-db", action="store_true", help="SQLite 스키마 초기화")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logging(SETTINGS)

    if args.init_db:
        Database(SETTINGS.db_path).initialize()
        logging.getLogger(__name__).info("DB 초기화 완료: %s", SETTINGS.db_path)
        return 0
    if args.run_once:
        try:
            CollectionPipeline(SETTINGS).run()
            return 0
        except Exception:
            # The pipeline already persists the failed run and logs the traceback.
            return 1

    run_scheduler(SETTINGS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
