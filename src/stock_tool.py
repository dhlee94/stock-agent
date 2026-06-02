"""
Stock signal tools — wraps StockBrain into two independent functions:
  - get_news_sentiment(ticker, name, market)  → FinBERT sentiment
  - get_price_forecast(ticker, name, market)  → Chronos forecast

The agent (planner/summarizer) decides how to combine these two signals.
If the underlying models cannot be loaded (missing deps, no network for the
first HuggingFace download, OOM, etc.), the functions return a clear
`{"status": "error", ...}` payload so the agent can route around them
instead of silently consuming fake data.
"""
import sys
import os
import base64
import json
from datetime import datetime, timedelta
import pytz

# Monkey patch for libraries using deprecated base64.decodestring
if not hasattr(base64, "decodestring"):
    base64.decodestring = base64.decodebytes

STOCK_PREDICTOR_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stock-price-predictor")
sys.path.insert(0, STOCK_PREDICTOR_PATH)

os.environ["USE_TORCH"] = "1"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

_stock_brain_cache = {}


def get_stock_brain(ticker: str, name: str, market: str):
    """
    Lazily build (and cache) a StockBrain per market.
    FinBERT and Moirai models are market-specific but ticker-agnostic,
    so caching by market avoids reloading heavy models for every new ticker.
    The loader is updated per call so data always reflects the requested ticker.
    """
    if market not in _stock_brain_cache:
        from main import StockBrain  # heavy imports happen here, on first use
        print(f"🔄 [StockTool] Initializing Brain for market={market} (ticker={ticker})...")
        _stock_brain_cache[market] = StockBrain(ticker, name, market)
    brain = _stock_brain_cache[market]
    # Update loader symbol/name so data fetching targets the requested ticker
    brain.loader.symbol = ticker
    brain.loader.name = name
    return brain


def _market_format(market: str):
    if market == "US":
        return pytz.timezone("US/Eastern"), "$", ",.2f"
    return pytz.timezone("Asia/Seoul"), "₩", ",.0f"


def get_news_sentiment(ticker: str, name: str, market: str = "KR") -> dict:
    """
    FinBERT sentiment of recent news for `ticker`.
    INDEPENDENT signal — does not consult price.
    """
    try:
        brain = get_stock_brain(ticker, name, market)
        tz, _, _ = _market_format(market)
        prep = brain.loader.prepare_all()
        sentiment = brain.get_news_sentiment(prep.get("news"))
        return {
            "status": "success",
            "ticker": ticker,
            "name": name,
            "market": market,
            "timestamp": datetime.now(tz).isoformat(),
            **sentiment,
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "ticker": ticker,
            "tool": "news_sentiment",
            "error": f"{type(e).__name__}: {e}",
        }


def get_price_forecast(ticker: str, name: str, market: str = "KR",
                       forecast_steps: int = 30, context_period: str = None) -> dict:
    """
    Chronos quantile price forecast for the next `forecast_steps` periods.
    INDEPENDENT signal — does not consult news.
    Automatically uses multivariate (Chronos-2) or univariate (Chronos-Bolt/v1)
    based on the CHRONOS_MODEL env var.
    """
    try:
        brain = get_stock_brain(ticker, name, market)
        tz, currency, fmt = _market_format(market)
        forecast = brain.get_price_forecast(forecast_steps=forecast_steps, context_period=context_period)
        cur_price = forecast.get("current_price", 0)

        last_date = datetime.now(tz)
        forecast_dates = [(last_date + timedelta(days=i + 1)).strftime("%Y-%m-%d") for i in range(forecast_steps)]
        forecast_data = [
            {
                "date": forecast_dates[i],
                "price": forecast["median"][i] if i < len(forecast.get("median", [])) else None,
                "lower": forecast["lower_q10"][i] if i < len(forecast.get("lower_q10", [])) else None,
                "upper": forecast["upper_q90"][i] if i < len(forecast.get("upper_q90", [])) else None,
            }
            for i in range(forecast_steps)
        ]

        return {
            "status": "success",
            "ticker": ticker,
            "name": name,
            "market": market,
            "timestamp": datetime.now(tz).isoformat(),
            "current_price": f"{currency}{cur_price:{fmt}}",
            "current_price_raw": cur_price,
            "forecast_steps": forecast.get("forecast_steps", forecast_steps),
            "final_median": forecast.get("final_median"),
            "pct_change": forecast.get("pct_change"),
            "direction": forecast.get("direction"),
            "forecast_data": forecast_data,
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "ticker": ticker,
            "tool": "price_forecast",
            "error": f"{type(e).__name__}: {e}",
        }


def get_price_forecast_moirai(ticker: str, name: str, market: str = "KR",
                               forecast_steps: int = 30, context_period: str = None) -> dict:
    """
    Moirai 2.0 quantile price forecast for the next `forecast_steps` periods.
    Requires MOIRAI_ENABLED=true in env. INDEPENDENT signal — does not consult news.
    """
    try:
        brain = get_stock_brain(ticker, name, market)
        tz, currency, fmt = _market_format(market)
        forecast = brain.get_price_forecast_moirai(forecast_steps=forecast_steps, context_period=context_period)
        if forecast.get("status") == "error":
            return forecast

        cur_price = forecast.get("current_price", 0)
        last_date = datetime.now(tz)
        forecast_dates = [(last_date + timedelta(days=i + 1)).strftime("%Y-%m-%d") for i in range(forecast_steps)]
        forecast_data = [
            {
                "date": forecast_dates[i],
                "price": forecast["median"][i] if i < len(forecast.get("median", [])) else None,
                "lower": forecast["lower_q10"][i] if i < len(forecast.get("lower_q10", [])) else None,
                "upper": forecast["upper_q90"][i] if i < len(forecast.get("upper_q90", [])) else None,
            }
            for i in range(forecast_steps)
        ]

        return {
            "status": "success",
            "ticker": ticker,
            "name": name,
            "market": market,
            "model": forecast.get("model"),
            "timestamp": datetime.now(tz).isoformat(),
            "current_price": f"{currency}{cur_price:{fmt}}",
            "current_price_raw": cur_price,
            "forecast_steps": forecast.get("forecast_steps", forecast_steps),
            "final_median": forecast.get("final_median"),
            "pct_change": forecast.get("pct_change"),
            "direction": forecast.get("direction"),
            "forecast_data": forecast_data,
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "ticker": ticker,
            "tool": "price_forecast_moirai",
            "error": f"{type(e).__name__}: {e}",
        }


if __name__ == "__main__":
    print(json.dumps(get_news_sentiment("005930.KS", "Samsung Electronics", "KR"), ensure_ascii=False, indent=2))
    print(json.dumps(get_price_forecast("005930.KS", "Samsung Electronics", "KR"), ensure_ascii=False, indent=2))
