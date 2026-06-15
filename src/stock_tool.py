"""
Stock signal tools — wraps StockBrain into independent functions:
  - get_news_sentiment(ticker, name, market)  → FinBERT sentiment

The agent (planner/summarizer) decides how to use this signal.
If the underlying models cannot be loaded, the functions return a clear
`{"status": "error", ...}` payload.
"""
import sys
import os
import base64
import json
from datetime import datetime
import pytz

# Monkey patch for libraries using deprecated base64.decodestring
if not hasattr(base64, "decodestring"):
    base64.decodestring = base64.decodebytes

STOCK_PREDICTOR_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stock-price-predictor")
sys.path.insert(0, STOCK_PREDICTOR_PATH)

os.environ["USE_TORCH"] = "1"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

import threading
_stock_brain_cache = {}
_stock_brain_lock = threading.Lock()


def get_stock_brain(ticker: str, name: str, market: str):
    """
    Lazily build (and cache) a StockBrain per market.
    FinBERT models are market-specific but ticker-agnostic.
    """
    if market not in _stock_brain_cache:
        with _stock_brain_lock:
            if market not in _stock_brain_cache:
                from main import StockBrain
                print(f"🔄 [StockTool] Initializing Brain for market={market} (ticker={ticker})...")
                _stock_brain_cache[market] = StockBrain(ticker, name, market)

    brain = _stock_brain_cache[market]
    brain.loader.symbol = ticker
    brain.loader.name = name
    brain.loader.market_type = market
    return brain


def _market_format(market: str):
    if market == "US":
        return pytz.timezone("US/Eastern"), "$", ",.2f"
    return pytz.timezone("Asia/Seoul"), "₩", ",.0f"


def get_news_sentiment(ticker: str, name: str, market: str = "KR") -> dict:
    """
    FinBERT sentiment of recent news for `ticker`.
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


if __name__ == "__main__":
    print(json.dumps(get_news_sentiment("005930.KS", "Samsung Electronics", "KR"), ensure_ascii=False, indent=2))
