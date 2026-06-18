from __future__ import annotations

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from crawler.config import Settings
from crawler.pipeline import CollectionPipeline

logger = logging.getLogger(__name__)


def run_scheduler(settings: Settings) -> None:
    scheduler = BlockingScheduler(timezone=settings.schedule_timezone)
    scheduler.add_job(
        CollectionPipeline(settings).run,
        trigger=CronTrigger(
            hour=settings.schedule_hour,
            minute=settings.schedule_minute,
            timezone=settings.schedule_timezone,
        ),
        id="daily_agent_b_collection",
        name="Daily Agent B data collection",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60 * 60,
    )

    logger.info(
        "스케줄러 시작: source=%s 매일 %02d:%02d (%s)",
        settings.source,
        settings.schedule_hour,
        settings.schedule_minute,
        settings.schedule_timezone,
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("스케줄러 종료")
