"""
Memento MCP Server - Stock Expert Edition

This server exposes professional stock analysis tools via MCP protocol.
"""
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env before anything else so MOIRAI_ENABLED is available at import time
load_dotenv(Path(__file__).parent.parent / ".env")

# Add src directory to path for imports when running as script
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SRC_DIR)

from mcp.server.fastmcp import FastMCP

MOIRAI_ENABLED  = os.environ.get("MOIRAI_ENABLED",  "true").lower()  == "true"
CHRONOS_ENABLED = os.environ.get("CHRONOS_ENABLED", "false").lower() == "true"

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
    news_sentiment,
    price_forecast,
    price_forecast_moirai,
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

# Prediction accuracy
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
def stock_dcf(ticker: str, market: str = "KR", margin_of_safety: float = 0.25) -> str:
    """
    Estimate intrinsic value per share via a lightweight DCF (FCFF off yfinance).
    Returns a bear/base/bull intrinsic-value range, a margin-of-safety "buy below"
    price, upside vs current price, and every assumption used (growth, discount
    rate, beta, terminal growth). Use this for a valuation-based target price
    instead of a moving-average. Declines gracefully ("DCF 산출 불가") when FCF,
    shares, or price data is missing — common for some KR tickers.
    Args:
        ticker: Stock ticker (e.g. "AAPL", "011070.KS")
        market: "KR" or "US"
        margin_of_safety: haircut on base intrinsic value for the buy price (default 0.25 = 25%)
    """
    return get_dcf(ticker, market=market, margin_of_safety=margin_of_safety)


@mcp.tool()
def stock_news(ticker: str = None, query: str = None, limit: int = 10, source: str = "auto") -> str:
    """
    Get latest stock or market news.

    Args:
        ticker: Stock ticker for company-specific news.
        query: Search query — pass any user-emphasized event/term/topic
               (translated to the market's language). Without `query`,
               only a generic feed is returned.
        limit: Max number of articles (default 10).
        source: News source selection. One of:
                  - "auto"     : (default) Route KR tickers to Naver (if keys
                                 configured) for richer Korean coverage; US
                                 tickers to yfinance.
                  - "naver"    : Force Naver Open API. Best for Korean tickers
                                 (.KS suffix) and Korean-language news.
                                 Falls back to yfinance if NAVER_* keys missing.
                  - "yfinance" : Force Yahoo Finance + Google News fallback.
                                 No API key required. Best for US tickers and
                                 as a global fallback.
                Prefer 'naver' for KR tickers (better headlines, more sources),
                'yfinance' for US tickers, 'auto' when unsure.
    """
    try:
        return get_market_news(ticker, query, limit, source)
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
def stock_news_sentiment(ticker: str, name: str, market: str = "KR") -> str:
    """
    FinBERT sentiment of recent news for the ticker.
    Returns an aggregate distribution {positive, neutral, negative}, the
    dominant label, and per-headline labels with scores. This is an
    INDEPENDENT signal — it does not look at price.

    Combine with `stock_chronos_forecast` and explain agreement / conflict
    explicitly. Sentiment dominance does not, by itself, justify a trade.

    Args:
        ticker: Stock ticker symbol (e.g., "005930.KS", "NVDA")
        name: Company name (e.g., "Samsung Electronics", "NVIDIA")
        market: "KR" or "US"
    """
    return news_sentiment(ticker, name, market)


if CHRONOS_ENABLED:
    @mcp.tool()
    def stock_chronos_forecast(ticker: str, name: str, market: str = "KR",
                                forecast_steps: int = 5, context_period: str = None) -> str:
        """
        Chronos-2 multivariate price forecast (Close + Volume + H-L range covariates).
        Returns median pct_change, direction (up/down), and the full
        median / q10 / q90 trajectory. INDEPENDENT signal — does not look at news.

        context_period: same semantics as stock_moirai_forecast. None = auto.

        Args:
            ticker: Stock ticker symbol
            name: Company name
            market: "KR" or "US"
            forecast_steps: Number of future steps to predict (default 5). Planner may adjust based on user intent.
            context_period: Historical window, e.g. '1mo','3mo','6mo','1y','2y'. None = auto.
        """
        return price_forecast(ticker, name, market, forecast_steps, context_period)


if MOIRAI_ENABLED:
    @mcp.tool()
    def stock_moirai_forecast(ticker: str, name: str, market: str = "KR",
                               forecast_steps: int = 5, context_period: str = None) -> str:
        """
        Moirai 2.0 quantile price forecast (primary forecaster).
        Returns median pct_change, direction (up/down), and the full
        median / q10 / q90 trajectory. INDEPENDENT signal — does not look at news.

        context_period controls how much historical data the model sees.
        Omit it (None) for the auto-default (≈5× forecast_steps in trading days).
        Override it when the situation calls for a different window:
          - '1mo'  : 급등락·이벤트 직후 → 최근 흐름만 반영
          - '3mo'  : 단기 모멘텀 중심
          - '6mo'  : 중장기 추세 반영
          - '1y'   : 계절성·장기 추세 반영
          - '2y'   : 경기 사이클 전체 포함

        Args:
            ticker: Stock ticker symbol
            name: Company name
            market: "KR" or "US"
            forecast_steps: Number of future steps to predict (default 5). Planner adjusts based on user intent.
            context_period: Historical window, e.g. '1mo','3mo','6mo','1y','2y'. None = auto.
        """
        return price_forecast_moirai(ticker, name, market, forecast_steps, context_period)


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
    Uses technical analysis (Bollinger Bands, Support/Resistance) plus the
    Chronos price forecast as an optional directional prior.
    Call this AFTER stock_technical (and optionally stock_chronos_forecast).
    Args:
        ticker: Stock ticker symbol
        market: "KR" or "US"
    """
    import json
    from risk_manager import calculate_risk_levels

    try:
        price_data = json.loads(get_stock_price(ticker, market))
        if price_data.get("status") == "error":
            return json.dumps({"error": f"Failed to get price: {price_data.get('error')}"})
        current_price = price_data.get("current_price", 0)

        tech_data = json.loads(technical_analysis(ticker))
        if tech_data.get("status") == "error":
            return json.dumps({"error": f"Failed to get technical data: {tech_data.get('error')}"})

        # Directional prior from the primary ENABLED forecaster. Moirai is the
        # primary model (MOIRAI_ENABLED default true); Chronos is a secondary
        # fallback (default off). Previously only Chronos was consulted, so with
        # the default config the AI prior was always absent and the target price
        # degenerated to a pure-technical level (ai_predicted_change_pct=0).
        ai_prediction = None
        name = price_data.get("name", ticker)
        for enabled, forecast_fn in ((MOIRAI_ENABLED, price_forecast_moirai),
                                     (CHRONOS_ENABLED, price_forecast)):
            if not enabled:
                continue
            try:
                forecast_data = json.loads(forecast_fn(ticker, name, market))
                if forecast_data.get("status") == "error":
                    continue
                pct = forecast_data.get("pct_change")
                if pct is not None:
                    ai_prediction = {"predicted_change_pct": pct}
                    break
            except Exception:
                continue

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


@mcp.tool()
def get_forecast_accuracy(ticker: str) -> str:
    """
    Return historical 5-day direction forecast accuracy for a ticker,
    grouped by context_period used. Call this BEFORE stock_moirai_forecast
    to choose the context_period that performed best for this ticker.

    Returns accuracy_pct per context_period (requires ≥3 evaluated predictions).
    If no history yet, returns empty list — use default context_period.

    Example output:
      [{"context_period": "1mo", "total": 8, "hits": 6, "accuracy_pct": 75.0},
       {"context_period": "2mo", "total": 5, "hits": 3, "accuracy_pct": 60.0}]
    """
    import json
    try:
        rows = _get_forecast_accuracy(ticker)
        if not rows:
            # Fall back to global summary
            global_rows = get_global_accuracy_summary()
            return json.dumps({
                "ticker": ticker,
                "ticker_history": [],
                "global_summary": global_rows,
                "note": "No ticker-specific history yet. Global summary shown."
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

    # MCP uses stdout as a pure JSONRPC channel (line-delimited).
    # Any print() from tool handlers corrupts the stream → redirect all
    # print() globally to stderr before mcp.run() takes over stdout.
    _real_print = _builtins.print
    def _stderr_print(*args, **kwargs):
        kwargs.setdefault("file", _sys.stderr)
        _real_print(*args, **kwargs)
    _builtins.print = _stderr_print

    chronos_status = "enabled" if CHRONOS_ENABLED else "disabled"
    moirai_status  = "enabled" if MOIRAI_ENABLED  else "disabled"
    print(f"🚀 MCP Server started | moirai [{moirai_status}] | chronos [{chronos_status}]")
    mcp.run()
