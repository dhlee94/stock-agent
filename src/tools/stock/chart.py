"""
Stock Chart Tool - Historical price data and chart analysis
"""
import yfinance as yf
from datetime import datetime
import pytz
from utils.response import ToolResponse


def get_stock_chart(ticker: str, period: str = "1mo", interval: str = "1d") -> str:
    """
    Get historical stock price data for charting.
    Args:
        ticker: Stock ticker symbol
        period: Data period - "1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "max"
        interval: Data interval - "1m", "5m", "15m", "1h", "1d", "1wk", "1mo"
    Returns:
        JSON with OHLCV data and summary statistics
    """
    print(f"📊 [Chart] Getting {period} chart for: {ticker}")
    
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period=period, interval=interval)
        
        if hist.empty:
            return ToolResponse.error("No data available", {"ticker": ticker})
        
        # Calculate summary statistics
        prices = hist['Close'].tolist()
        start_price = prices[0]
        end_price = prices[-1]
        total_return = ((end_price - start_price) / start_price) * 100
        
        high_price = max(prices)
        low_price = min(prices)
        avg_price = sum(prices) / len(prices)
        # price_range_percent: (high - low) / avg — 단순 가격 범위 비율
        price_range_percent = (high_price - low_price) / avg_price * 100 if avg_price else 0.0
        # volatility_percent: 일간 수익률의 표준편차 (표준 금융 변동성)
        returns = [
            (prices[i] - prices[i - 1]) / prices[i - 1]
            for i in range(1, len(prices)) if prices[i - 1] != 0
        ]
        if len(returns) > 1:
            mean_r = sum(returns) / len(returns)
            volatility = (sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)) ** 0.5 * 100
        else:
            volatility = 0.0
        
        # Convert to list of OHLCV records (last 30 points max for API response)
        data_points = []
        for idx in hist.tail(30).index:
            row = hist.loc[idx]
            data_points.append({
                "date": idx.strftime("%Y-%m-%d %H:%M"),
                "open": round(row['Open'], 2),
                "high": round(row['High'], 2),
                "low": round(row['Low'], 2),
                "close": round(row['Close'], 2),
                "volume": int(row['Volume'])
            })
        
        return ToolResponse.success({
            "ticker": ticker,
            "period": period,
            "interval": interval,
            "data_points": len(data_points),
            "summary": {
                "start_price": round(start_price, 2),
                "end_price": round(end_price, 2),
                "total_return_percent": round(total_return, 2),
                "high": round(high_price, 2),
                "low": round(low_price, 2),
                "average": round(avg_price, 2),
                "price_range_percent": round(price_range_percent, 2),
                "volatility_percent": round(volatility, 4)
            },
            "chart_data": data_points
        })

    except Exception as e:
        return ToolResponse.error(str(e), {"ticker": ticker})
