"""
Stock Tool - AI-powered stock analysis using Chronos + FinBERT
"""
import json
from ..stock_tool import analyze_stock as _analyze_stock


def analyze_stock(ticker: str, name: str, market: str = "KR") -> str:
    """
    Analyze a stock using AI (Chronos + FinBERT multimodal fusion).
    Returns current price, AI sentiment score, and buy/sell recommendation.
    Args:
        ticker: Stock ticker symbol (e.g., "005930.KS" for Samsung, "NVDA" for NVIDIA)
        name: Company name (e.g., "Samsung Electronics", "NVIDIA")
        market: "KR" for Korean stocks, "US" for US stocks
    """
    print(f"📈 [Stock] Analyzing: {name} ({ticker}) in {market} market")
    try:
        result = _analyze_stock(ticker, name, market)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)})
