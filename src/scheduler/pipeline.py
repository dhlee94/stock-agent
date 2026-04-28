from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from .bot import TelegramBot
from .config import SchedulerConfig

try:
    from ..agent_client import MementoAgent
except ImportError:
    from agent_client import MementoAgent


logger = logging.getLogger(__name__)


def _build_task(ticker: str) -> str:
    return f"{ticker} 종목을 분석하고 매매 추천(목표가/손절가 포함)을 해주세요."


async def run_once(config: SchedulerConfig) -> int:
    """Run analysis for every ticker in the watchlist and dispatch via Telegram.

    Returns the number of analyses successfully delivered.
    """
    bot = TelegramBot(token=config.telegram_bot_token, chat_id=config.telegram_chat_id)
    agent = MementoAgent()

    now = datetime.now(ZoneInfo(config.timezone))
    await bot.send_digest_header(len(config.watchlist), now)

    delivered = 0
    for ticker in config.watchlist:
        logger.info("Analyzing %s ...", ticker)
        try:
            result = await agent.run_for_web(_build_task(ticker))
        except Exception as e:
            logger.exception("Analysis failed for %s", ticker)
            await bot.send_text(f"⚠️ <b>{ticker}</b> 분석 실패: {type(e).__name__}: {e}")
            continue

        await bot.send_ticker_analysis(ticker, result)
        delivered += 1
        # Throttle a touch so Telegram doesn't rate-limit us on long watchlists.
        await asyncio.sleep(1.0)

    logger.info("Delivered %d / %d analyses", delivered, len(config.watchlist))
    return delivered


def run_once_sync(config: SchedulerConfig) -> int:
    return asyncio.run(run_once(config))
