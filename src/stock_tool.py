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
import pandas as pd
from database import save_prediction, init_db
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
    # Update loader so data fetching targets the requested ticker
    brain.loader.symbol = ticker
    brain.loader.name = name
    brain.loader.market_type = market  # defensive: keep in sync with cache key
    return brain


def _market_format(market: str):
    if market == "US":
        return pytz.timezone("US/Eastern"), "$", ",.2f"
    return pytz.timezone("Asia/Seoul"), "₩", ",.0f"


def _biz_dates(start: datetime, n: int) -> list:
    """Return n business days (Mon–Fri) starting after start date."""
    dates = pd.bdate_range(start=start + timedelta(days=1), periods=n)
    return [d.strftime("%Y-%m-%d") for d in dates]


def _last_data_datetime(last_data_date: str, tz) -> datetime:
    """Convert ISO date string from forecast result to tz-aware datetime.
    Falls back to now() when the string is absent (e.g. Chronos v1 path).
    """
    if last_data_date:
        naive = datetime.strptime(last_data_date, "%Y-%m-%d")
        return tz.localize(naive)
    return datetime.now(tz)


def _trajectory_shape(medians: list, cur_price: float) -> dict:
    """
    예측 궤적의 방향 전환 감지.
    - turning_point: 최고점/최저점이 중간에 있으면 전환 인덱스 반환
    - shape: 'up', 'down', 'up_then_down', 'down_then_up'
    - short_dir / long_dir: 전반부/후반부 방향
    """
    if not medians or len(medians) < 4:
        return {"shape": "unknown"}

    n = len(medians)
    mid = n // 2
    short_pct = (medians[mid - 1] - cur_price) / cur_price * 100
    long_pct = (medians[-1] - cur_price) / cur_price * 100
    short_dir = "up" if short_pct > 0 else "down"
    long_dir = "up" if long_pct > 0 else "down"

    if short_dir == long_dir:
        shape = short_dir
    elif short_dir == "up" and long_dir == "down":
        shape = "up_then_down"
    else:
        shape = "down_then_up"

    result = {"shape": shape, "short_dir": short_dir, "long_dir": long_dir,
              "short_pct": round(short_pct, 2), "long_pct": round(long_pct, 2)}

    # 전환점 위치 (최고점 or 최저점 인덱스)
    if shape == "up_then_down":
        result["turning_day"] = int(np.argmax(medians)) + 1
    elif shape == "down_then_up":
        result["turning_day"] = int(np.argmin(medians)) + 1

    return result


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

        last_date = _last_data_datetime(forecast.get("last_data_date"), tz)
        forecast_dates = _biz_dates(last_date, forecast_steps)
        forecast_data = [
            {
                "date": forecast_dates[i],
                "price": forecast["median"][i] if i < len(forecast.get("median", [])) else None,
                "lower": forecast["lower_q10"][i] if i < len(forecast.get("lower_q10", [])) else None,
                "upper": forecast["upper_q90"][i] if i < len(forecast.get("upper_q90", [])) else None,
            }
            for i in range(forecast_steps)
        ]

        trajectory = _trajectory_shape(forecast.get("median", []), cur_price)

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
            "trajectory": trajectory,
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
        last_date = _last_data_datetime(forecast.get("last_data_date"), tz)
        forecast_dates = _biz_dates(last_date, forecast_steps)
        forecast_data = [
            {
                "date": forecast_dates[i],
                "price": forecast["median"][i] if i < len(forecast.get("median", [])) else None,
                "lower": forecast["lower_q10"][i] if i < len(forecast.get("lower_q10", [])) else None,
                "upper": forecast["upper_q90"][i] if i < len(forecast.get("upper_q90", [])) else None,
            }
            for i in range(forecast_steps)
        ]

        # 단기 예측(<= 10 step)만 피드백 루프용으로 DB에 저장
        if forecast_steps <= 10 and forecast.get("direction") and cur_price:
            try:
                init_db()
                target_date = forecast_dates[-1]  # 5번째 영업일
                save_prediction(
                    ticker=ticker, market=market,
                    context_period=context_period or "auto",
                    forecast_steps=forecast_steps,
                    predicted_at=last_date.strftime("%Y-%m-%d"),
                    target_date=target_date,
                    current_price=cur_price,
                    predicted_direction=forecast["direction"],
                    predicted_pct=forecast.get("pct_change", 0),
                    model=forecast.get("model", ""),
                )
                print(f"📝 [PredictionLog] {ticker} direction={forecast['direction']} target={target_date}")
            except Exception as log_err:
                print(f"⚠️  [PredictionLog] save failed: {log_err}")

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
            "trajectory": _trajectory_shape(forecast.get("median", []), cur_price),
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
