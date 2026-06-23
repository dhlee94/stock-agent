"""
Technical Analysis Tool - RSI, MACD, Bollinger Bands, Moving Averages
"""
import json
import yfinance as yf
import numpy as np
from typing import List
from utils.response import ToolResponse
from .market_utils import get_company_name


def _calculate_rsi(prices: List[float], period: int = 14) -> float:
    """Calculate RSI using Wilder's smoothing (standard definition)."""
    if len(prices) < period + 1:
        return None

    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    # Seed with simple average of the first `period` values
    avg_gain = float(np.mean(gains[:period]))
    avg_loss = float(np.mean(losses[:period]))

    # Wilder's EMA for the remaining values (smoothing factor = 1/period)
    for g, l in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


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
    """EMA seeded with SMA of the first `period` values (standard definition)."""
    alpha = 2 / (period + 1)
    ema = np.zeros_like(data, dtype=float)
    ema[period - 1] = np.mean(data[:period])
    for i in range(period, len(data)):
        ema[i] = alpha * data[i] + (1 - alpha) * ema[i - 1]
    return ema


def _calculate_bollinger_bands(prices: List[float], period: int = 20, std_dev: int = 2) -> dict:
    """Calculate Bollinger Bands"""
    if len(prices) < period:
        return None
    
    prices = np.array(prices)
    sma = np.mean(prices[-period:])
    std = np.std(prices[-period:], ddof=1)  # sample std (Bollinger standard definition)
    
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


def _calculate_support_resistance(highs: List[float], lows: List[float],
                                  current: float, lookback: int = 5) -> dict:
    """Derive support/resistance from real swing pivots in the OHLCV window.

    A swing high is a High that is the maximum within ±`lookback` bars (a local
    top → resistance); a swing low is the symmetric local bottom → support. From
    those pivots we return the nearest support at/below the current price and the
    nearest resistance at/above it, plus the absolute window range as a guaranteed
    fallback. Every number here is an actual traded price from the data — this is
    the field that stops the analyst from inventing levels (e.g. a phantom $72.31)
    when none were ever computed."""
    highs = np.asarray(highs, dtype=float)
    lows = np.asarray(lows, dtype=float)
    n = len(highs)

    swing_highs: List[float] = []
    swing_lows: List[float] = []
    for i in range(lookback, n - lookback):
        window_h = highs[i - lookback:i + lookback + 1]
        window_l = lows[i - lookback:i + lookback + 1]
        if highs[i] == window_h.max():
            swing_highs.append(float(highs[i]))
        if lows[i] == window_l.min():
            swing_lows.append(float(lows[i]))

    window_low = round(float(lows.min()), 2)
    window_high = round(float(highs.max()), 2)

    supports_below = [p for p in swing_lows if p <= current]
    resists_above = [p for p in swing_highs if p >= current]
    support = round(max(supports_below), 2) if supports_below else window_low
    resistance = round(min(resists_above), 2) if resists_above else window_high

    return {
        "support": support,
        "resistance": resistance,
        "window_low": window_low,
        "window_high": window_high,
        "current": round(float(current), 2),
        "pivot_count": {"support": len(swing_lows), "resistance": len(swing_highs)},
        "method": "swing pivots (±%d bars) over the analyzed window" % lookback,
    }


def technical_analysis(ticker: str, period: str = "6mo") -> str:
    """
    Perform comprehensive technical analysis on a stock.
    Args:
        ticker: Stock ticker symbol
        period: Data period for analysis ("1mo", "3mo", "6mo", "1y")
    Returns:
        Standardized JSON response
    """
    print(f"📈 [Technical] Analyzing: {ticker}")
    
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period=period)

        # Fallback to progressively longer periods when data is sparse
        if hist.empty or len(hist) < 20:
            for fallback in ["3mo", "6mo", "1y"]:
                if fallback == period:
                    continue
                hist = stock.history(period=fallback)
                if not hist.empty and len(hist) >= 20:
                    period = fallback
                    break

        if hist.empty or len(hist) < 20:
            return ToolResponse.error("Insufficient data for analysis")
        
        prices = hist['Close'].tolist()
        volumes = hist['Volume'].tolist()
        highs = hist['High'].tolist()
        lows = hist['Low'].tolist()

        # Calculate all indicators
        rsi = _calculate_rsi(prices)
        macd = _calculate_macd(prices)
        bollinger = _calculate_bollinger_bands(prices)
        moving_avgs = _calculate_moving_averages(prices)
        support_resistance = _calculate_support_resistance(highs, lows, prices[-1])
        
        # Volume analysis
        avg_volume = np.mean(volumes[-20:])
        current_volume = volumes[-1]
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1
        
        # Generate overall signal
        signals = []
        
        if rsi is not None:
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
        
        return ToolResponse.success({
            "ticker": ticker,
            "company_name": get_company_name(ticker),
            "period": period,
            "indicators": {
                "rsi": {"value": rsi, "signal": "oversold" if rsi is not None and rsi < 30 else "overbought" if rsi is not None and rsi > 70 else "neutral"},
                "macd": macd,
                "bollinger_bands": bollinger,
                "moving_averages": moving_avgs,
                "support_resistance": support_resistance,
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
        })
        
    except Exception as e:
        return ToolResponse.error(str(e), {"ticker": ticker})
