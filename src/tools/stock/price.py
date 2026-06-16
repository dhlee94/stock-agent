"""
Stock Price Tool - Real-time stock price retrieval
"""
import json
import re
import yfinance as yf
from datetime import datetime, timedelta
import pytz
from utils.response import ToolResponse


def detect_market(ticker: str, declared: str = "KR") -> str:
    """Infer the correct market from the ticker's shape, overriding a wrong
    `declared` value.

    `market` defaults to "KR" everywhere, so when the agent omits it for a US
    ticker (e.g. NFLX) the request is routed into the Korean FinanceDataReader
    path, which returns NaN/garbage prices that then propagate silently through
    DCF and risk calculations. KR tickers are numeric, optionally suffixed
    .KS/.KQ; anything alphabetic is a US ticker regardless of what was declared.
    """
    t = ticker.strip().upper()
    base = t.split(".")[0]
    if t.endswith(".KS") or t.endswith(".KQ") or base.isdigit():
        return "KR"
    if re.fullmatch(r"[A-Z][A-Z.\-]*", base):
        return "US"
    return declared


def get_stock_price(ticker: str, market: str = "KR") -> str:
    """
    Get real-time stock price and basic info.
    Args:
        ticker: Stock ticker symbol (e.g., "005930.KS" for Samsung, "AAPL" for Apple)
        market: "KR" for Korean stocks, "US" for US stocks
    Returns:
        Standardized JSON response
    """
    # Route by the ticker's actual shape, not just the (often-defaulted) market arg.
    market = detect_market(ticker, market)
    print(f"💰 [Price] Getting price for: {ticker} (market={market})")

    try:
        # Korea Market: Use FinanceDataReader
        if market == "KR":
            import FinanceDataReader as fdr
            
            code = ticker.split('.')[0] 
            
            # Get data for the last 30 days to ensure we have at least 2 trading days
            start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
            df = fdr.DataReader(code, start=start_date)
            df = df.tail(2)
            
            if df.empty:
                return ToolResponse.error(f"Failed to fetch price data for {ticker} (KR) via FDR.")
            
            current_price = float(df['Close'].iloc[-1])
            prev_close = float(df['Close'].iloc[-2]) if len(df) > 1 else float(df['Open'].iloc[-1])
            
            change = current_price - prev_close
            change_pct = (change / prev_close) * 100 if prev_close != 0 else 0.0
            
            volume = int(df['Volume'].iloc[-1])
            day_high = float(df['High'].iloc[-1])
            day_low = float(df['Low'].iloc[-1])
            
            from .market_utils import get_company_name
            stock_name = get_company_name(ticker) or ticker

            return ToolResponse.success({
                "ticker": ticker,
                "name": stock_name,
                "current_price": round(current_price, 0),
                "previous_close": round(prev_close, 0),
                "change": round(change, 0),
                "change_percent": round(change_pct, 2),
                "currency": "KRW",
                "volume": volume,
                "day_high": round(day_high, 0),
                "day_low": round(day_low, 0),
                "timestamp": datetime.now(pytz.timezone('Asia/Seoul')).isoformat(),
                "source": "FinanceDataReader"
            })

        # US Market: Use yfinance
        stock = yf.Ticker(ticker)
        info = stock.info
        # Fetch a few extra sessions: the most recent bar is often a partial/empty
        # row with a NaN Close (today's session not yet settled). Taking .iloc[-1]
        # blindly propagates that NaN downstream — that is the "invalid price: nan"
        # that breaks the risk/reward calc. Drop NaN closes and use the last valid bar.
        hist = stock.history(period="5d")
        hist = hist.dropna(subset=['Close'])

        if hist.empty:
            return ToolResponse.error(f"Failed to fetch price data for {ticker}. Check ticker symbol.")

        last = hist.iloc[-1]
        current_price = last['Close']
        prev_close = hist['Close'].iloc[-2] if len(hist) > 1 else current_price
        change = current_price - prev_close
        change_pct = (change / prev_close) * 100 if prev_close != 0 else 0.0

        tz = pytz.timezone('US/Eastern') if market == "US" else pytz.timezone('Asia/Seoul')
        currency = "USD" if market == "US" else "KRW"
        
        return ToolResponse.success({
            "ticker": ticker,
            "name": info.get('shortName', info.get('longName', ticker)),
            "current_price": round(current_price, 2),
            "previous_close": round(prev_close, 2),
            "change": round(change, 2),
            "change_percent": round(change_pct, 2),
            "currency": currency,
            "volume": int(last['Volume']),
            "day_high": round(last['High'], 2),
            "day_low": round(last['Low'], 2),
            "market_cap": info.get('marketCap'),
            "52_week_high": info.get('fiftyTwoWeekHigh'),
            "52_week_low": info.get('fiftyTwoWeekLow'),
            "timestamp": datetime.now(tz).isoformat(),
            "source": "yfinance"
        })
        
    except Exception as e:
        return ToolResponse.error(f"Failed to fetch price data for {ticker}: {str(e)}")

