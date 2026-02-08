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
        # Korea Market: Use FinanceDataReader
        if market == "KR":
            import FinanceDataReader as fdr
            
            # FDR treats "005930.KS" as "005930" ideally, but handles extensions too.
            # Best to strip extension for FDR if it's purely checking KRX, 
            # but FDR's data_reader handles "005930" well.
            code = ticker.split('.')[0] 
            
            # Get 2 days of data
            df = fdr.DataReader(code, datetime.now().year - 1) # fetch enough to be safe, then tail
            df = df.tail(2)
            
            if df.empty:
                raise ValueError(f"Failed to fetch price data for {ticker} (KR) via FDR.")
            
            current_price = float(df['Close'].iloc[-1])
            prev_close = float(df['Close'].iloc[-2]) if len(df) > 1 else float(df['Open'].iloc[-1]) # Fallback
            
            change = current_price - prev_close
            change_pct = (change / prev_close) * 100 if prev_close != 0 else 0.0
            
            volume = int(df['Volume'].iloc[-1])
            day_high = float(df['High'].iloc[-1])
            day_low = float(df['Low'].iloc[-1])
            
            # Additional Info (Name is harder with just FDR, might need yfinance fallback or hardcode)
            # For now, let's keep the name from yfinance if possible, or just use ticker
            stock_name = ticker 
            try:
                # Optional: Fetch name from yfinance as metadata fallback
                stock_name = yf.Ticker(ticker).info.get('shortName', ticker)
            except:
                pass

            return json.dumps({
                "status": "success",
                "ticker": ticker,
                "name": stock_name,
                "current_price": round(current_price, 0), # KRW is integer-like
                "previous_close": round(prev_close, 0),
                "change": round(change, 0),
                "change_percent": round(change_pct, 2),
                "currency": "KRW",
                "volume": volume,
                "day_high": round(day_high, 0),
                "day_low": round(day_low, 0),
                "market_cap": "N/A", # FDR doesn't provide real-time market cap easily without listing
                "52_week_high": "N/A",
                "52_week_low": "N/A",
                "timestamp": datetime.now(pytz.timezone('Asia/Seoul')).isoformat(),
                "source": "FinanceDataReader"
            }, ensure_ascii=False)

        # US Market: Use yfinance
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
            "timestamp": datetime.now(tz).isoformat(),
            "source": "yfinance"
        }, ensure_ascii=False)
        
    except ValueError:
        raise  # Re-raise ValueError for retry logic
    except Exception as e:
        raise ValueError(f"Failed to fetch price data for {ticker}: {str(e)}")

