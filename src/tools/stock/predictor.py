"""
Stock signal MCP wrappers — now only news sentiment remains:
  - news_sentiment: FinBERT-based sentiment of recent headlines
"""
import json
import sys
import os

TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.dirname(TOOLS_DIR)
sys.path.insert(0, SRC_DIR)

from stock_tool import (
    get_news_sentiment as _get_news_sentiment,
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


def price_forecast(ticker: str, name: str, market: str = "KR",
                   forecast_steps: int = 30, context_period: str = None) -> str:
    """Legacy wrapper — forecasting models removed."""
    return json.dumps({"status": "error", "error": "Price forecasting models (Chronos) removed for light mode."})


def price_forecast_moirai(ticker: str, name: str, market: str = "KR",
                           forecast_steps: int = 30, context_period: str = None) -> str:
    """Legacy wrapper — forecasting models removed."""
    return json.dumps({"status": "error", "error": "Price forecasting models (Moirai) removed for light mode."})
