"""
Stock Analysis Tool - Wrapper for StockBrain
"""
import sys
import os

# Add stock-price-predictor to path
STOCK_PREDICTOR_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stock-price-predictor")
sys.path.insert(0, STOCK_PREDICTOR_PATH)

# Suppress TensorFlow logs
os.environ["USE_TORCH"] = "1"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

import json
from datetime import datetime
import pytz

# Lazy loading to avoid slow startup
_stock_brain_cache = {}

def get_stock_brain(ticker: str, name: str, market: str):
    """Get or create a StockBrain instance (cached)."""
    cache_key = f"{ticker}_{market}"
    if cache_key not in _stock_brain_cache:
        from main import StockBrain
        _stock_brain_cache[cache_key] = StockBrain(ticker, name, market)
    return _stock_brain_cache[cache_key]

def analyze_stock(ticker: str, name: str, market: str = "KR") -> dict:
    """
    Analyze a stock using AI (Chronos + FinBERT fusion).
    
    Args:
        ticker: Stock ticker symbol (e.g., "005930.KS" for Samsung, "NVDA" for NVIDIA)
        name: Company name (e.g., "Samsung Electronics", "NVIDIA")
        market: "KR" for Korean stocks, "US" for US stocks
    
    Returns:
        dict with analysis results
    """
    try:
        brain = get_stock_brain(ticker, name, market)
        
        # Get timezone and formatting based on market
        if market == "US":
            tz = pytz.timezone('US/Eastern')
            currency = "$"
            fmt = ",.2f"
        else:
            tz = pytz.timezone('Asia/Seoul')
            currency = "₩"
            fmt = ",.0f"
        
        # Prepare data
        prep = brain.loader.prepare_all()
        stl = brain.loader.get_stl_features(brain.loader.fetch_price_data())
        
        # Extract features and run fusion
        import torch
        text_feat, price_feat = brain.extract_features(prep['news'], prep['price_context'])
        
        with torch.no_grad():
            fused_vector = brain.fusion(text_feat, price_feat)
            score = torch.sigmoid(brain.classifier(fused_vector)).item()
            is_bullish = score > 0.5
        
        # Chronos forecast
        context_tensor = torch.tensor(prep['price_context'])
        forecast = brain.chronos.predict(context_tensor, 5)
        chronos_pred = forecast[0].quantile(0.5).item()
        
        # Determine recommendation
        cur_price = prep['current_price']
        trend_direction = None
        if stl:
            trend = stl['trend']
            trend_direction = "UP" if trend > cur_price else "DOWN"
            
            if is_bullish and trend > cur_price:
                recommendation = "STRONG BUY"
            elif not is_bullish and trend < cur_price:
                recommendation = "STRONG SELL"
            else:
                recommendation = "HOLD"
        else:
            recommendation = "BUY" if is_bullish else "SELL"
        
        return {
            "status": "success",
            "ticker": ticker,
            "name": name,
            "market": market,
            "timestamp": datetime.now(tz).isoformat(),
            "current_price": f"{currency}{cur_price:{fmt}}",
            "current_price_raw": cur_price,
            "ai_score": round(score, 4),
            "sentiment": "Bullish" if is_bullish else "Bearish",
            "chronos_forecast": f"{currency}{chronos_pred:{fmt}}",
            "trend_direction": trend_direction,
            "recommendation": recommendation,
            "top_news": prep['news'][0][:100] if prep['news'] else None
        }
        
    except Exception as e:
        return {
            "status": "error",
            "ticker": ticker,
            "error": str(e)
        }

if __name__ == "__main__":
    # Test
    result = analyze_stock("005930.KS", "Samsung Electronics", "KR")
    print(json.dumps(result, ensure_ascii=False, indent=2))
