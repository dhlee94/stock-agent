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
    get_price_forecast_moirai as _get_price_forecast_moirai,
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
    print(f"🔮 [PriceForecast] {name} ({ticker}) — {forecast_steps} steps, ctx={context_period or 'auto'}")
    try:
        return json.dumps(
            _get_price_forecast(ticker, name, market, forecast_steps, context_period),
            ensure_ascii=False,
        )
    except Exception as e:
        return json.dumps({"status": "error", "ticker": ticker, "error": str(e)})


def price_forecast_moirai(ticker: str, name: str, market: str = "KR",
                           forecast_steps: int = 30, context_period: str = None) -> str:
    print(f"🔮 [MoiraiForecast] {name} ({ticker}) — {forecast_steps} steps, ctx={context_period or 'auto'}")
    try:
        return json.dumps(
            _get_price_forecast_moirai(ticker, name, market, forecast_steps, context_period),
            ensure_ascii=False,
        )
    except Exception as e:
        return json.dumps({"status": "error", "ticker": ticker, "error": str(e)})
