"""
AI Stock Predictor Tool - Using Chronos + FinBERT for prediction
This wraps the existing stock_tool.py predictor.
"""
import json
import sys
import os

# Add parent directories to path for stock_tool import
TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.dirname(TOOLS_DIR)
sys.path.insert(0, SRC_DIR)

from stock_tool import analyze_stock as _predict


def analyze_stock_ai(ticker: str, name: str, market: str = "KR") -> str:
    """
    Analyze a stock using AI (Chronos + FinBERT multimodal fusion).
    Returns current price, AI sentiment score, and buy/sell recommendation.
    Args:
        ticker: Stock ticker symbol (e.g., "005930.KS" for Samsung, "NVDA" for NVIDIA)
        name: Company name (e.g., "Samsung Electronics", "NVIDIA")
        market: "KR" for Korean stocks, "US" for US stocks
    Returns:
        JSON with AI analysis including sentiment, prediction, and recommendation
    """
    print(f"🤖 [AI Predictor] Analyzing: {name} ({ticker})")
    
    try:
        result = _predict(ticker, name, market)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "status": "error",
            "ticker": ticker,
            "error": str(e)
        })
