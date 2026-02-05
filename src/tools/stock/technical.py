"""
Technical Analysis Tool - RSI, MACD, Bollinger Bands, Moving Averages
"""
import json
import yfinance as yf
import numpy as np
from typing import List


def _calculate_rsi(prices: List[float], period: int = 14) -> float:
    """Calculate Relative Strength Index"""
    if len(prices) < period + 1:
        return None
    
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    
    if avg_loss == 0:
        return 100.0
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return round(rsi, 2)


def _calculate_macd(prices: List[float]) -> dict:
    """Calculate MACD (Moving Average Convergence Divergence)"""
    if len(prices) < 26:
        return None
    
    prices = np.array(prices)
    
    # Calculate EMAs
    ema12 = _ema(prices, 12)
    ema26 = _ema(prices, 26)
    
    macd_line = ema12 - ema26
    signal_line = _ema(macd_line, 9)
    histogram = macd_line - signal_line
    
    return {
        "macd": round(macd_line[-1], 4),
        "signal": round(signal_line[-1], 4),
        "histogram": round(histogram[-1], 4),
        "trend": "bullish" if histogram[-1] > 0 else "bearish"
    }


def _ema(data: np.ndarray, period: int) -> np.ndarray:
    """Calculate Exponential Moving Average"""
    alpha = 2 / (period + 1)
    ema = np.zeros_like(data)
    ema[0] = data[0]
    for i in range(1, len(data)):
        ema[i] = alpha * data[i] + (1 - alpha) * ema[i-1]
    return ema


def _calculate_bollinger_bands(prices: List[float], period: int = 20, std_dev: int = 2) -> dict:
    """Calculate Bollinger Bands"""
    if len(prices) < period:
        return None
    
    prices = np.array(prices)
    sma = np.mean(prices[-period:])
    std = np.std(prices[-period:])
    
    upper = sma + (std_dev * std)
    lower = sma - (std_dev * std)
    current = prices[-1]
    
    # Position within bands (0 = lower, 0.5 = middle, 1 = upper)
    position = (current - lower) / (upper - lower) if upper != lower else 0.5
    
    return {
        "upper": round(upper, 2),
        "middle": round(sma, 2),
        "lower": round(lower, 2),
        "current": round(current, 2),
        "position": round(position, 2),
        "signal": "overbought" if position > 0.8 else "oversold" if position < 0.2 else "neutral"
    }


def _calculate_moving_averages(prices: List[float]) -> dict:
    """Calculate various moving averages"""
    prices = np.array(prices)
    current = prices[-1]
    
    ma_periods = [5, 10, 20, 50, 100, 200]
    mas = {}
    signals = []
    
    for period in ma_periods:
        if len(prices) >= period:
            ma = np.mean(prices[-period:])
            mas[f"ma{period}"] = round(ma, 2)
            signals.append("bullish" if current > ma else "bearish")
    
    # Overall signal based on majority
    bullish_count = signals.count("bullish")
    total = len(signals)
    
    return {
        "values": mas,
        "current_price": round(current, 2),
        "bullish_signals": bullish_count,
        "bearish_signals": total - bullish_count,
        "overall": "bullish" if bullish_count > total / 2 else "bearish"
    }


def technical_analysis(ticker: str, period: str = "6mo") -> str:
    """
    Perform comprehensive technical analysis on a stock.
    Args:
        ticker: Stock ticker symbol
        period: Data period for analysis ("1mo", "3mo", "6mo", "1y")
    Returns:
        JSON with RSI, MACD, Bollinger Bands, Moving Averages, and trading signals
    """
    print(f"📈 [Technical] Analyzing: {ticker}")
    
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period=period)
        
        if hist.empty or len(hist) < 30:
            return json.dumps({"status": "error", "error": "Insufficient data for analysis"})
        
        prices = hist['Close'].tolist()
        volumes = hist['Volume'].tolist()
        
        # Calculate all indicators
        rsi = _calculate_rsi(prices)
        macd = _calculate_macd(prices)
        bollinger = _calculate_bollinger_bands(prices)
        moving_avgs = _calculate_moving_averages(prices)
        
        # Volume analysis
        avg_volume = np.mean(volumes[-20:])
        current_volume = volumes[-1]
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1
        
        # Generate overall signal
        signals = []
        
        if rsi:
            if rsi < 30:
                signals.append(("RSI", "oversold", "bullish"))
            elif rsi > 70:
                signals.append(("RSI", "overbought", "bearish"))
            else:
                signals.append(("RSI", "neutral", "neutral"))
        
        if macd:
            signals.append(("MACD", macd['trend'], macd['trend']))
        
        if bollinger:
            if bollinger['signal'] == "oversold":
                signals.append(("Bollinger", "oversold", "bullish"))
            elif bollinger['signal'] == "overbought":
                signals.append(("Bollinger", "overbought", "bearish"))
            else:
                signals.append(("Bollinger", "neutral", "neutral"))
        
        signals.append(("MA", moving_avgs['overall'], moving_avgs['overall']))
        
        # Calculate overall recommendation
        bullish = sum(1 for s in signals if s[2] == "bullish")
        bearish = sum(1 for s in signals if s[2] == "bearish")
        
        if bullish >= 3:
            recommendation = "STRONG BUY"
        elif bullish >= 2:
            recommendation = "BUY"
        elif bearish >= 3:
            recommendation = "STRONG SELL"
        elif bearish >= 2:
            recommendation = "SELL"
        else:
            recommendation = "HOLD"
        
        return json.dumps({
            "status": "success",
            "ticker": ticker,
            "period": period,
            "indicators": {
                "rsi": {"value": rsi, "signal": "oversold" if rsi and rsi < 30 else "overbought" if rsi and rsi > 70 else "neutral"},
                "macd": macd,
                "bollinger_bands": bollinger,
                "moving_averages": moving_avgs,
            },
            "volume": {
                "current": int(current_volume),
                "average_20d": int(avg_volume),
                "ratio": round(volume_ratio, 2),
                "signal": "high" if volume_ratio > 1.5 else "low" if volume_ratio < 0.5 else "normal"
            },
            "signals": [{"indicator": s[0], "condition": s[1], "bias": s[2]} for s in signals],
            "recommendation": recommendation,
            "confidence": max(bullish, bearish) / len(signals) if signals else 0
        }, ensure_ascii=False)
        
    except Exception as e:
        return json.dumps({"status": "error", "ticker": ticker, "error": str(e)})
