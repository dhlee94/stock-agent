"""
Stock Price Tool - Real-time stock price retrieval
"""
import json
import yfinance as yf
from datetime import datetime
import pytz


def get_stock_price(ticker: str, market: str = "KR") -> str:
    """
    Get real-time stock price and basic info.
    Args:
        ticker: Stock ticker symbol (e.g., "005930.KS" for Samsung, "AAPL" for Apple)
        market: "KR" for Korean stocks, "US" for US stocks
    Returns:
        JSON with current price, change, volume, and market status
    Raises:
        ValueError: If no price data available (to trigger retry logic)
    """
    print(f"💰 [Price] Getting price for: {ticker}")
    
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        hist = stock.history(period="2d")
        
        if hist.empty:
            raise ValueError(f"Failed to fetch price data for {ticker}. Check if the ticker symbol is correct.")
        
        current_price = hist['Close'].iloc[-1]
        prev_close = hist['Close'].iloc[-2] if len(hist) > 1 else current_price
        change = current_price - prev_close
        change_pct = (change / prev_close) * 100
        
        # Get timezone based on market
        if market == "US":
            tz = pytz.timezone('US/Eastern')
            currency = "USD"
        else:
            tz = pytz.timezone('Asia/Seoul')
            currency = "KRW"
        
        return json.dumps({
            "status": "success",
            "ticker": ticker,
            "name": info.get('shortName', info.get('longName', ticker)),
            "current_price": round(current_price, 2),
            "previous_close": round(prev_close, 2),
            "change": round(change, 2),
            "change_percent": round(change_pct, 2),
            "currency": currency,
            "volume": int(hist['Volume'].iloc[-1]),
            "day_high": round(hist['High'].iloc[-1], 2),
            "day_low": round(hist['Low'].iloc[-1], 2),
            "market_cap": info.get('marketCap'),
            "52_week_high": info.get('fiftyTwoWeekHigh'),
            "52_week_low": info.get('fiftyTwoWeekLow'),
            "timestamp": datetime.now(tz).isoformat()
        }, ensure_ascii=False)
        
    except ValueError:
        raise  # Re-raise ValueError for retry logic
    except Exception as e:
        raise ValueError(f"Failed to fetch price data for {ticker}: {str(e)}")

