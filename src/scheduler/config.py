from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List

from dotenv import load_dotenv


@dataclass
class SchedulerConfig:
    telegram_bot_token: str
    telegram_chat_id: str

    watchlist: List[str] = field(default_factory=list)

    run_hour: int = 12
    run_minute: int = 0
    timezone: str = "Asia/Seoul"

    @classmethod
    def from_env(cls) -> "SchedulerConfig":
        load_dotenv()

        def required(key: str) -> str:
            value = os.getenv(key)
            if not value:
                raise RuntimeError(f"Missing required environment variable: {key}")
            return value

        watchlist_raw = os.getenv("SCHEDULER_WATCHLIST", "")
        watchlist = [t.strip() for t in watchlist_raw.split(",") if t.strip()]
        if not watchlist:
            raise RuntimeError(
                "SCHEDULER_WATCHLIST is empty. Set it to a comma-separated "
                "list of tickers, e.g. SCHEDULER_WATCHLIST=005930.KS,000660.KS"
            )

        return cls(
            telegram_bot_token=required("TELEGRAM_BOT_TOKEN").strip(),
            telegram_chat_id=required("TELEGRAM_CHAT_ID").strip(),
            watchlist=watchlist,
            run_hour=int(os.getenv("SCHEDULER_RUN_HOUR", "12")),
            run_minute=int(os.getenv("SCHEDULER_RUN_MINUTE", "0")),
            timezone=os.getenv("SCHEDULER_TIMEZONE", "Asia/Seoul").strip(),
        )
