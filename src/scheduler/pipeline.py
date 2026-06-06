from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from .bot import TelegramBot
from .config import SchedulerConfig

try:
    from ..agent_client import MementoAgent
    from ..database import get_pending_predictions, evaluate_prediction, init_db
except ImportError:
    from agent_client import MementoAgent
    from database import get_pending_predictions, evaluate_prediction, init_db


logger = logging.getLogger(__name__)


def _build_task(ticker: str) -> str:
    return f"{ticker} 종목을 분석하고 매매 추천(목표가/손절가 포함)을 해주세요."


def _evaluate_pending_predictions(tz_name: str) -> int:
    """
    target_date가 지난 미평가 예측을 실제 가격으로 채점한다.
    Returns number of predictions evaluated.
    """
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    try:
        import yfinance as yf
    except ImportError:
        logger.warning("yfinance not available — skipping prediction evaluation")
        return 0

    init_db()
    today = datetime.now(ZoneInfo(tz_name)).strftime("%Y-%m-%d")
    pending = get_pending_predictions(today)
    if not pending:
        logger.info("No pending predictions to evaluate.")
        return 0

    evaluated = 0
    for pred in pending:
        ticker = pred["ticker"]
        target_date = pred["target_date"]
        base_price = pred["current_price"]
        try:
            from datetime import timedelta
            target_dt = datetime.strptime(target_date, "%Y-%m-%d")
            end_dt = target_dt + timedelta(days=7)  # buffer for holidays
            hist = yf.Ticker(ticker).history(
                start=target_date,
                end=end_dt.strftime("%Y-%m-%d"),
                interval="1d",
            )
            if hist.empty:
                continue
            # target_date 당일 또는 그 이후 첫 거래일 종가 사용
            actual_price = float(hist["Close"].iloc[0])
            actual_dir = "up" if actual_price >= base_price else "down"
            evaluate_prediction(
                pred_id=pred["id"],
                actual_price=actual_price,
                actual_direction=actual_dir,
                evaluated_at=today,
            )
            result = "✅" if pred["predicted_direction"] == actual_dir else "❌"
            logger.info(
                "Evaluated %s [%s]: predicted=%s actual=%s %s",
                ticker, target_date, pred["predicted_direction"], actual_dir, result,
            )
            evaluated += 1
        except Exception as e:
            logger.warning("Evaluation failed for %s: %s", ticker, e)

    logger.info("Evaluated %d predictions.", evaluated)
    return evaluated


async def run_once(config: SchedulerConfig) -> int:
    """Run analysis for every ticker in the watchlist and dispatch via Telegram.

    Returns the number of analyses successfully delivered.
    """
    bot = TelegramBot(token=config.telegram_bot_token, chat_id=config.telegram_chat_id)
    agent = MementoAgent()

    now = datetime.now(ZoneInfo(config.timezone))

    # 예측 평가 먼저 실행 (오늘 날짜 기준)
    evaluated = _evaluate_pending_predictions(config.timezone)
    if evaluated:
        logger.info("Pre-run evaluation: scored %d predictions", evaluated)

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
