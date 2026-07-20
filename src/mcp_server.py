"""
Memento MCP Server - Stock Expert Edition

This server exposes professional stock analysis tools via MCP protocol.
"""
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env before anything else
load_dotenv(Path(__file__).parent.parent / ".env")

# Add src directory to path for imports
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SRC_DIR)

from mcp.server.fastmcp import FastMCP

# Stock Tools
from tools.stock import (
    get_stock_price,
    get_stock_chart,
    get_financials,
    get_dcf,
    get_market_news,
    technical_analysis,
    compare_stocks,
    get_sector_analysis,
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

# Prediction accuracy (legacy support for DB view, though models are removed)
from database import get_forecast_accuracy as _get_forecast_accuracy, get_global_accuracy_summary

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
def stock_dcf(ticker: str, market: str = "KR", margin_of_safety: float = 0.25,
              growth_override: float = None) -> str:
    """
    Estimate intrinsic value per share via a lightweight two-stage DCF.

    The headline fields (fair_value, intrinsic_value, buy_below_price, upside) are
    ALWAYS data-derived and identical for a given ticker on every call — the base
    case anchors to revenue growth when the FCF-history CAGR diverges high, and the
    output is a hedged range (see growth_consistency). growth_override does NOT move
    those headline fields; it only adds a separate, clearly-labeled `override_scenario`
    what-if block. So re-running with a thesis/catalyst rate never contradicts the
    canonical valuation — prefer omitting it unless you specifically want the scenario.

    Args:
        ticker: Stock ticker
        market: "KR" or "US"
        margin_of_safety: haircut on intrinsic value (buy_below = fair_value × (1−MOS))
        growth_override: explicit stage-1 annual growth as a decimal (0.17 = 17%) for
            an ALTERNATIVE scenario only; the canonical headline stays data-derived.
            Omit to report just the data-derived valuation.
    """
    return get_dcf(ticker, market=market, margin_of_safety=margin_of_safety,
                   growth_override=growth_override)


@mcp.tool()
def stock_news(ticker: str = None, query: str = None, limit: int = 10, source: str = "auto",
               max_age_days: int = 30) -> str:
    """
    Get latest stock or market news.
    Args:
        ticker: Stock ticker for company-specific news.
        query: Search query
        limit: Max number of articles (default 10).
        source: News source selection ("auto", "naver", "yfinance").
        max_age_days: Only return articles newer than this many days (default 30),
            so stale news cannot be read as current. Widen it only when the query
            is explicitly about an older, dated event.
    """
    try:
        return get_market_news(ticker, query, limit, source, max_age_days=max_age_days)
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
        tickers: Comma-separated ticker symbols
        period: Comparison period
    """
    ticker_list = [t.strip() for t in tickers.split(",")]
    return compare_stocks(ticker_list, period)


@mcp.tool()
def stock_sector(sector: str = None, market: str = "KR") -> str:
    """
    Analyze market sectors.
    Args:
        sector: Sector name
        market: "KR" or "US"
    """
    return get_sector_analysis(sector, market)


@mcp.tool()
def analyze_drivers(ticker: str, name: str = "") -> str:
    """
    Analyze historical volatility to identify key price drivers.
    Args:
        ticker: Stock ticker symbol
        name: Company name (optional)
    """
    try:
        return _analyze_drivers(ticker, name)
    except Exception as e:
        return f'{{"error": "Driver Analysis Error: {str(e)}"}}'


@mcp.tool()
def analyze_peers(ticker: str, similarity_threshold: float = 0.7, compare_with: list = None) -> str:
    """
    Analyze peer group using trend similarity.
    Args:
        ticker: Stock ticker symbol
        similarity_threshold: Minimum correlation for reference proxy
        compare_with: List of tickers to compare with
    """
    return analyze_peer_group(ticker, similarity_threshold, compare_with)


@mcp.tool()
def calculate_risk(ticker: str, market: str = "KR") -> str:
    """
    Calculate Target Price, Stop-loss, and Risk/Reward ratio using technical levels.
    Args:
        ticker: Stock ticker symbol
        market: "KR" or "US"
    """
    import json
    from risk_manager import calculate_risk_levels
    from tools.stock import detect_market

    try:
        # Route by the ticker's actual shape — a US ticker left at the default
        # market="KR" otherwise lands in the Korean price path and returns NaN.
        market = detect_market(ticker, market)
        price_data = json.loads(get_stock_price(ticker, market))
        if price_data.get("status") == "error":
            return json.dumps({"error": f"Failed to get price: {price_data.get('message') or price_data.get('error')}"})
        current_price = price_data.get("current_price", 0)

        tech_data = json.loads(technical_analysis(ticker))
        if tech_data.get("status") == "error":
            return json.dumps({"error": f"Failed to get technical data: {tech_data.get('message') or tech_data.get('error')}"})

        # AI prediction consult removed to keep codebase light
        result = calculate_risk_levels(current_price, tech_data, None)
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
    """Calculate math expressions."""
    return calculate_math(expression)


@mcp.tool()
def read_file(filepath: str) -> str:
    """Read a document file."""
    return read_document(filepath)


@mcp.tool()
def save_memory(task: str, plan: str, result: str, feedback_score: float) -> str:
    """Save analysis result to memory for future reference."""
    return save_feedback(task, plan, result, feedback_score)


@mcp.tool()
def get_forecast_accuracy(ticker: str) -> str:
    """
    Return historical direction forecast accuracy (if any exists in DB).
    Args:
        ticker: Stock ticker
    """
    import json
    try:
        rows = _get_forecast_accuracy(ticker)
        if not rows:
            global_rows = get_global_accuracy_summary()
            return json.dumps({
                "ticker": ticker,
                "ticker_history": [],
                "global_summary": global_rows,
                "note": "No ticker-specific history available."
            }, ensure_ascii=False)
        return json.dumps({
            "ticker": ticker,
            "ticker_history": rows,
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


# =========================================================
# Main Entry Point
# =========================================================
if __name__ == "__main__":
    import sys as _sys
    import builtins as _builtins

    _real_print = _builtins.print
    def _stderr_print(*args, **kwargs):
        kwargs.setdefault("file", _sys.stderr)
        _real_print(*args, **kwargs)
    _builtins.print = _stderr_print

    print(f"🚀 MCP Server started | ML forecasting disabled (light mode)")
    mcp.run()
