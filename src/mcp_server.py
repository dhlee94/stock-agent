"""
Memento MCP Server - Stock Expert Edition

This server exposes professional stock analysis tools via MCP protocol.
"""
import sys
import os

# Add src directory to path for imports when running as script
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SRC_DIR)

from mcp.server.fastmcp import FastMCP

# Stock Tools
from tools.stock import (
    get_stock_price,
    get_stock_chart,
    get_financials,
    get_market_news,
    technical_analysis,
    compare_stocks,
    get_sector_analysis,
    analyze_stock_ai,
    analyze_peer_group,
)

# Utility Tools
from tools import (
    search_web,
    crawl_url,
    execute_python,
    calculate_math,
    read_document,
    save_feedback,
)

# Driver Memory
from driver_memory import analyze_drivers as _analyze_drivers

# Initialize MCP Server
mcp = FastMCP("Stock Expert Agent Tools")

# =========================================================
# 📈 Stock Analysis Tools
# =========================================================

@mcp.tool()
def stock_price(ticker: str, market: str = "KR") -> str:
    """
    Get real-time stock price with key metrics.
    Args:
        ticker: Stock ticker (e.g., "005930.KS" for Samsung, "AAPL" for Apple)
        market: "KR" for Korean stocks, "US" for US stocks
    """
    try:
        return get_stock_price(ticker, market)
    except Exception as e:
        return f'{{"error": "Stock Price Error: {str(e)}"}}'


@mcp.tool()
def stock_chart(ticker: str, period: str = "1mo", interval: str = "1d") -> str:
    """
    Get historical chart data with OHLCV.
    Args:
        ticker: Stock ticker symbol
        period: "1d", "5d", "1mo", "3mo", "6mo", "1y", "5y"
        interval: "1m", "5m", "15m", "1h", "1d", "1wk"
    """
    return get_stock_chart(ticker, period, interval)


@mcp.tool()
def stock_financials(ticker: str) -> str:
    """
    Get company fundamentals: PER, PBR, EPS, ROE, margins, debt ratio.
    Args:
        ticker: Stock ticker symbol
    """
    return get_financials(ticker)


@mcp.tool()
def stock_news(ticker: str = None, query: str = None, limit: int = 10) -> str:
    """
    Get latest stock or market news.
    Args:
        ticker: Stock ticker for company-specific news
        query: Search query for general market news
        limit: Max number of articles
    """
    try:
        return get_market_news(ticker, query, limit)
    except Exception as e:
        return f'{{"error": "Stock News Error: {str(e)}"}}'


@mcp.tool()
def stock_technical(ticker: str, period: str = "6mo") -> str:
    """
    Technical analysis: RSI, MACD, Bollinger Bands, Moving Averages.
    Args:
        ticker: Stock ticker symbol
        period: Analysis period ("1mo", "3mo", "6mo", "1y")
    """
    return technical_analysis(ticker, period)


@mcp.tool()
def stock_compare(tickers: str, period: str = "1y") -> str:
    """
    Compare multiple stocks on key metrics.
    Args:
        tickers: Comma-separated ticker symbols (e.g., "005930.KS,000660.KS,066570.KS")
        period: Comparison period
    """
    ticker_list = [t.strip() for t in tickers.split(",")]
    return compare_stocks(ticker_list, period)


@mcp.tool()
def stock_sector(sector: str = None, market: str = "KR") -> str:
    """
    Analyze market sectors (반도체, 2차전지, 바이오, Technology, etc.)
    Args:
        sector: Sector name (None for all sectors overview)
        market: "KR" or "US"
    """
    return get_sector_analysis(sector, market)


@mcp.tool()
def stock_ai_predict(ticker: str, name: str, market: str = "KR") -> str:
    """
    AI-powered prediction using Chronos + FinBERT multimodal fusion.
    Returns AI sentiment score and buy/sell recommendation.
    Args:
        ticker: Stock ticker symbol
        name: Company name
        market: "KR" or "US"
    """
    return analyze_stock_ai(ticker, name, market)


@mcp.tool()
def analyze_drivers(ticker: str, name: str = "") -> str:
    """
    Analyze historical volatility to identify key price drivers.
    Returns keywords that historically move this stock (e.g., HBM, 파업, 실적).
    Use this BEFORE searching for news to make targeted queries.
    Args:
        ticker: Stock ticker symbol (e.g., "005930.KS")
        name: Company name (optional)
    """
    try:
        return _analyze_drivers(ticker, name)
    except Exception as e:
        return f'{{"error": "Driver Analysis Error: {str(e)}"}}'


@mcp.tool()
def analyze_peers(ticker: str, similarity_threshold: float = 0.7, compare_with: list = None) -> str:
    """
    Analyze peer group using news entity mining or user-specified targets.
    
    Workflow:
    1. Entity Mining: Find co-mentioned companies from news (or use compare_with)
    2. Data Acquisition: Get 60-day closing prices
    3. STL Decomposition: Extract trend component
    4. Pearson Correlation: Calculate trend similarity
    5. Reference Proxy: Select peer with correlation > threshold
    
    Args:
        ticker: Stock ticker symbol (e.g., "005930.KS", "NVDA")
        similarity_threshold: Minimum correlation for reference proxy (default 0.7)
        compare_with: List of tickers to compare with (e.g., ["000660.KS"]). 
                     If provided, bypasses news mining and directly compares with these tickers.
    """
    return analyze_peer_group(ticker, similarity_threshold, compare_with)


@mcp.tool()
def calculate_risk(ticker: str, market: str = "KR") -> str:
    """
    Calculate Target Price, Stop-loss, and Risk/Reward ratio.
    Uses technical analysis (Bollinger Bands, Support/Resistance) and AI prediction.
    Call this AFTER stock_technical and stock_ai_predict for accurate results.
    Args:
        ticker: Stock ticker symbol
        market: "KR" or "US"
    """
    import json
    from risk_manager import calculate_risk_levels
    
    try:
        # Get current price
        price_data = json.loads(get_stock_price(ticker, market))
        if price_data.get("status") == "error":
            return json.dumps({"error": f"Failed to get price: {price_data.get('error')}"})
        current_price = price_data.get("current_price", 0)
        
        # Get technical data
        tech_data = json.loads(technical_analysis(ticker))
        if tech_data.get("status") == "error":
            return json.dumps({"error": f"Failed to get technical data: {tech_data.get('error')}"})
        
        # Get AI prediction (optional)
        try:
            ai_data = json.loads(analyze_stock_ai(ticker, price_data.get("name", ticker), market))
            ai_prediction = {"predicted_change_pct": ai_data.get("predicted_change_pct", 0)}
        except:
            ai_prediction = None
        
        # Calculate risk levels
        result = calculate_risk_levels(current_price, tech_data, ai_prediction)
        result["ticker"] = ticker
        result["market"] = market
        
        return json.dumps(result, ensure_ascii=False)
        
    except Exception as e:
        return json.dumps({"error": str(e)})


# =========================================================
# 🛠️ Utility Tools
# =========================================================

@mcp.tool()
def web_search(query: str) -> str:
    """Search the web for information."""
    return search_web(query)


@mcp.tool()
def web_crawl(url: str) -> str:
    """Crawl a URL and extract content."""
    return crawl_url(url)


@mcp.tool()
def run_python(code: str) -> str:
    """Execute Python code for analysis calculations."""
    return execute_python(code)


@mcp.tool()
def calc_math(expression: str) -> str:
    """Calculate math expressions (sqrt, sin, cos, log, etc.)"""
    return calculate_math(expression)


@mcp.tool()
def read_file(filepath: str) -> str:
    """Read a document file."""
    return read_document(filepath)


@mcp.tool()
def save_memory(task: str, plan: str, result: str, feedback_score: float) -> str:
    """Save analysis result to memory for future reference."""
    return save_feedback(task, plan, result, feedback_score)


# =========================================================
# Main Entry Point
# =========================================================
if __name__ == "__main__":
    print("🚀 Stock Expert MCP Server Started!")
    print("")
    print("📈 Stock Tools:")
    print("   stock_price, stock_chart, stock_financials, stock_news")
    print("   stock_technical, stock_compare, stock_sector, stock_ai_predict")
    print("")
    print("🛠️ Utility Tools:")
    print("   web_search, web_crawl, run_python, calc_math, read_file, save_memory")
    mcp.run()
