from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
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
        load_dotenv(Path(__file__).parent.parent.parent / ".env")

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

        def int_env(key: str, default: int) -> int:
            raw = os.getenv(key, str(default))
            try:
                return int(raw)
            except ValueError:
                raise RuntimeError(
                    f"Environment variable {key}={raw!r} must be an integer"
                )

        return cls(
            telegram_bot_token=required("TELEGRAM_BOT_TOKEN").strip(),
            telegram_chat_id=required("TELEGRAM_CHAT_ID").strip(),
            watchlist=watchlist,
            run_hour=int_env("SCHEDULER_RUN_HOUR", 12),
            run_minute=int_env("SCHEDULER_RUN_MINUTE", 0),
            timezone=os.getenv("SCHEDULER_TIMEZONE", "Asia/Seoul").strip(),
        )
