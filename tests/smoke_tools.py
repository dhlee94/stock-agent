"""
Tool smoke test — calls every tool the MCP server exposes with a representative
input and reports {OK / EMPTY / ERROR} plus latency, so we can see at a glance
which tools are actually working end-to-end (network, deps, models).

Run inside the app container:
    docker exec stock-agent-app python -m tests.smoke_tools
"""
import os
import sys
import json
import time
import traceback

# Mirror mcp_server import setup
SRC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
sys.path.insert(0, os.path.abspath(SRC_DIR))

MOIRAI_ENABLED = os.environ.get("MOIRAI_ENABLED", "true").lower() == "true"
CHRONOS_ENABLED = os.environ.get("CHRONOS_ENABLED", "false").lower() == "true"

KR = "005930.KS"      # Samsung Electronics
KR_NAME = "Samsung Electronics"
US = "AAPL"

results = []


def _classify(out):
    """Map a tool's raw string/dict output to OK / EMPTY / ERROR + short note."""
    raw = out if isinstance(out, str) else json.dumps(out, ensure_ascii=False)
    try:
        data = json.loads(raw) if isinstance(out, str) else out
    except Exception:
        # Non-JSON string output (some tools return plain text).
        # Flag known failure prefixes so e.g. web_crawl's "Failed to crawl..."
        # isn't silently counted as a success.
        low = raw.lower()
        if low.startswith("failed") or low.startswith("blocked") or "error:" in low:
            return "ERROR", raw[:160].replace("\n", " ")
        return ("OK" if raw and len(raw) > 10 else "EMPTY"), raw[:120]

    if isinstance(data, dict):
        if data.get("status") == "error" or "error" in data:
            return "ERROR", str(data.get("error") or data.get("message"))[:160]
        if not data or all(not v for v in data.values()):
            return "EMPTY", raw[:120]
    if isinstance(data, list) and len(data) == 0:
        return "EMPTY", "[]"
    return "OK", raw[:120].replace("\n", " ")


def check(name, fn):
    t0 = time.time()
    try:
        out = fn()
        status, note = _classify(out)
    except Exception as e:
        status, note = "ERROR", f"{type(e).__name__}: {e}"
        traceback.print_exc()
    dt = time.time() - t0
    results.append((name, status, f"{dt:6.2f}s", note))
    icon = {"OK": "✅", "EMPTY": "⚪", "ERROR": "❌"}[status]
    print(f"{icon} {name:28} {status:6} {dt:6.2f}s  {note}")


def main():
    print("=" * 90)
    print(f"TOOL SMOKE TEST  | MOIRAI={MOIRAI_ENABLED} CHRONOS={CHRONOS_ENABLED}")
    print("=" * 90)

    # --- Utility tools (lightweight, no market data) ---
    from tools import (search_web, crawl_url, execute_python,
                       calculate_math, read_document, save_feedback)
    check("web_search", lambda: search_web("Samsung Electronics stock", 3))
    check("web_crawl", lambda: crawl_url("https://example.com"))
    check("run_python", lambda: execute_python("x = sum([1,2,3]); print(x)"))
    check("calc_math", lambda: calculate_math("sqrt(16) + 2**3"))
    check("read_file", lambda: read_document("/app/requirements.txt"))

    # --- Stock data tools (yfinance / pykrx — network) ---
    from tools.stock import (get_stock_price, get_stock_chart, get_financials,
                             get_dcf, get_market_news, technical_analysis,
                             compare_stocks, get_sector_analysis)
    check("stock_price (KR)", lambda: get_stock_price(KR, "KR"))
    check("stock_price (US)", lambda: get_stock_price(US, "US"))
    check("stock_chart", lambda: get_stock_chart(KR, "1mo", "1d"))
    check("stock_financials", lambda: get_financials(KR))
    # US ticker exercises the happy path; KR tickers often decline (no FCF data)
    check("stock_dcf", lambda: get_dcf(US, market="US", margin_of_safety=0.25))
    check("stock_news", lambda: get_market_news(ticker=KR, limit=5))
    check("stock_technical", lambda: technical_analysis(KR))
    check("stock_compare", lambda: compare_stocks([KR, "000660.KS"], "6mo"))
    check("stock_sector", lambda: get_sector_analysis(market="KR"))

    # --- Driver / peer / risk (composite tools) ---
    from driver_memory import analyze_drivers
    from tools.stock import analyze_peer_group
    check("analyze_drivers", lambda: analyze_drivers(KR, KR_NAME))
    check("analyze_peers", lambda: analyze_peer_group(KR, 0.7, ["000660.KS"]))

    import json as _json
    from risk_manager import calculate_risk_levels
    def _risk():
        price = _json.loads(get_stock_price(KR, "KR"))
        tech = _json.loads(technical_analysis(KR))
        return calculate_risk_levels(price.get("current_price", 0), tech, None)
    check("calculate_risk", _risk)

    # --- Forecast accuracy (DB) ---
    from database import get_forecast_accuracy
    check("get_forecast_accuracy", lambda: get_forecast_accuracy(KR) or [])

    # --- Heavy ML tools (FinBERT / Moirai — model load + network) ---
    from tools.stock import news_sentiment, price_forecast_moirai
    check("stock_news_sentiment", lambda: news_sentiment(KR, KR_NAME, "KR"))
    if MOIRAI_ENABLED:
        check("stock_moirai_forecast",
              lambda: price_forecast_moirai(KR, KR_NAME, "KR", 5, None))
    if CHRONOS_ENABLED:
        from tools.stock import price_forecast
        check("stock_chronos_forecast",
              lambda: price_forecast(KR, KR_NAME, "KR", 5, None))

    # --- save_memory last (writes to store) ---
    check("save_memory",
          lambda: save_feedback("smoke test", "n/a", "n/a", 0.0))

    # --- Summary ---
    print("=" * 90)
    n_ok = sum(1 for _, s, _, _ in results if s == "OK")
    n_empty = sum(1 for _, s, _, _ in results if s == "EMPTY")
    n_err = sum(1 for _, s, _, _ in results if s == "ERROR")
    print(f"SUMMARY: {n_ok} OK | {n_empty} EMPTY | {n_err} ERROR  (total {len(results)})")
    if n_err or n_empty:
        print("\nNeeds attention:")
        for name, s, dt, note in results:
            if s in ("ERROR", "EMPTY"):
                print(f"  [{s}] {name}: {note}")
    print("=" * 90)
    return 1 if n_err else 0


if __name__ == "__main__":
    sys.exit(main())
