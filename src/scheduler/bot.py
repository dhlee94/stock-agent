from __future__ import annotations

import html
import logging
from datetime import datetime

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError


logger = logging.getLogger(__name__)


_RULE = "━━━━━━━━━━━━━━━━━━━━"
# Telegram hard limit is 4096; leave headroom for our header/footer wrapping.
_MAX_BODY_CHARS = 3600


class TelegramBot:
    def __init__(self, token: str, chat_id: str):
        self._bot = Bot(token=token)
        self._chat_id = chat_id

    async def send_digest_header(self, ticker_count: int, run_date: datetime) -> None:
        text = (
            f"📊 <b>일일 시장 분석</b>\n"
            f"<i>{run_date.strftime('%Y-%m-%d %H:%M %Z')}</i>\n"
            f"{_RULE}\n"
            f"분석 대상: {ticker_count}개 종목"
        )
        await self._send(text)

    async def send_ticker_analysis(self, ticker: str, analysis: str) -> None:
        body = analysis.strip() or "(분석 결과 없음)"
        if len(body) > _MAX_BODY_CHARS:
            body = body[:_MAX_BODY_CHARS] + "\n…(중략)"

        text = (
            f"📈 <b>{html.escape(ticker)}</b>\n"
            f"{_RULE}\n"
            f"{html.escape(body)}"
        )
        await self._send(text)

    async def send_text(self, text: str) -> None:
        await self._send(html.escape(text))

    async def _send(self, text: str) -> None:
        try:
            await self._bot.send_message(
                chat_id=self._chat_id,
                text=text[:4096],
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        except TelegramError:
            logger.exception("Telegram send failed")
