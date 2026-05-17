"""
Stock signal MCP wrappers — two independent tools:
  - news_sentiment: FinBERT-based sentiment of recent headlines
  - price_forecast: Chronos-based price forecast (median + q10/q90 bands)

These wrap `stock_tool.get_news_sentiment` / `stock_tool.get_price_forecast`.
The agent decides how to weigh the two signals.
"""
import json
import sys
import os

TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.dirname(TOOLS_DIR)
sys.path.insert(0, SRC_DIR)

from stock_tool import (
    get_news_sentiment as _get_news_sentiment,
    get_price_forecast as _get_price_forecast,
)


def news_sentiment(ticker: str, name: str, market: str = "KR") -> str:
    """
    FinBERT sentiment of recent news for the given ticker.
    Args:
        ticker: e.g. "005930.KS", "NVDA"
        name: e.g. "Samsung Electronics", "NVIDIA"
        market: "KR" or "US"
    Returns:
        JSON string with `distribution` (positive/neutral/negative),
        `dominant`, `headlines`, `count`.
    """
    print(f"📰 [NewsSentiment] {name} ({ticker})")
    try:
        return json.dumps(_get_news_sentiment(ticker, name, market), ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "ticker": ticker, "error": str(e)})


def price_forecast(ticker: str, name: str, market: str = "KR", forecast_steps: int = 30) -> str:
    """
    Chronos price forecast for the given ticker.
    Args:
        ticker: e.g. "005930.KS", "NVDA"
        name: e.g. "Samsung Electronics", "NVIDIA"
        market: "KR" or "US"
        forecast_steps: Number of future steps to predict (default 30)
    Returns:
        JSON string with `pct_change`, `direction`, `final_median`,
        `forecast_data` (per-day median/lower/upper).
    """
    print(f"🔮 [PriceForecast] {name} ({ticker}) — {forecast_steps} steps")
    try:
        return json.dumps(
            _get_price_forecast(ticker, name, market, forecast_steps),
            ensure_ascii=False,
        )
    except Exception as e:
        return json.dumps({"status": "error", "ticker": ticker, "error": str(e)})
