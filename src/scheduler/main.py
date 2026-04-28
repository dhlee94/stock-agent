from __future__ import annotations

import argparse
import logging
import sys
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

try:
    from .config import SchedulerConfig
    from .pipeline import run_once_sync
except ImportError:
    from scheduler.config import SchedulerConfig
    from scheduler.pipeline import run_once_sync


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("agent_scheduler")


def _job(config: SchedulerConfig) -> None:
    try:
        logger.info("Starting scheduled run...")
        delivered = run_once_sync(config)
        logger.info("Run complete — delivered %d analyses", delivered)
    except Exception as e:
        logger.error("Scheduled run failed with error: %s", str(e), exc_info=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stock Expert AI — daily watchlist digest")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single analyze-and-deliver cycle and exit (no scheduling).",
    )
    args = parser.parse_args(argv)

    try:
        config = SchedulerConfig.from_env()
    except Exception as e:
        logger.error("Failed to load configuration: %s", str(e))
        return 1

    if args.once:
        try:
            delivered = run_once_sync(config)
            logger.info("One-shot run delivered %d analyses", delivered)
            return 0
        except Exception as e:
            logger.error("One-shot run failed: %s", str(e), exc_info=True)
            return 1

    tz = ZoneInfo(config.timezone)
    scheduler = BlockingScheduler(timezone=tz)
    scheduler.add_job(
        _job,
        trigger=CronTrigger(hour=config.run_hour, minute=config.run_minute, timezone=tz),
        args=[config],
        id="agent_daily_digest",
        replace_existing=True,
    )
    logger.info(
        "Scheduled daily run at %02d:%02d %s for %d ticker(s): %s",
        config.run_hour,
        config.run_minute,
        config.timezone,
        len(config.watchlist),
        ", ".join(config.watchlist),
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down scheduler...")
        if scheduler.running:
            scheduler.shutdown()
    except Exception as e:
        logger.error("Scheduler crashed: %s", str(e), exc_info=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
