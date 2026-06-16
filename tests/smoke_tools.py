"""
Tool smoke test — calls every tool the MCP server exposes.
"""
import os
import sys
import json
import time
import traceback

SRC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
sys.path.insert(0, os.path.abspath(SRC_DIR))

KR = "005930.KS"
KR_NAME = "Samsung Electronics"
US = "AAPL"

results = []

def _classify(out):
    raw = out if isinstance(out, str) else json.dumps(out, ensure_ascii=False)
    try:
        data = json.loads(raw) if isinstance(out, str) else out
    except Exception:
        low = raw.lower()
        if low.startswith("failed") or low.startswith("blocked") or "error:" in low:
            return "ERROR", raw[:160]
        return ("OK" if raw and len(raw) > 10 else "EMPTY"), raw[:120]

    if isinstance(data, dict):
        if data.get("status") == "error" or "error" in data:
            return "ERROR", str(data.get("error") or data.get("message"))[:160]
        if not data or all(not v for v in data.values()):
            return "EMPTY", raw[:120]
    return "OK", raw[:120]

def check(name, fn):
    t0 = time.time()
    try:
        out = fn()
        status, note = _classify(out)
    except Exception as e:
        status, note = "ERROR", f"{type(e).__name__}: {e}"
    dt = time.time() - t0
    results.append((name, status, f"{dt:6.2f}s", note))
    icon = {"OK": "✅", "EMPTY": "⚪", "ERROR": "❌"}[status]
    print(f"{icon} {name:28} {status:6} {dt:6.2f}s  {note}")

def main():
    from tools import (search_web, crawl_url, execute_python, calculate_math, read_document, save_feedback)
    check("web_search", lambda: search_web("Samsung Electronics stock"))
    check("web_crawl", lambda: crawl_url("https://example.com"))
    check("run_python", lambda: execute_python("print(1+1)"))
    check("calc_math", lambda: calculate_math("4+4"))
    check("read_file", lambda: read_document("/app/requirements.txt"))

    from tools.stock import (get_stock_price, get_stock_chart, get_financials, get_dcf, get_market_news, technical_analysis, compare_stocks, get_sector_analysis)
    check("stock_price (KR)", lambda: get_stock_price(KR, "KR"))
    check("stock_chart", lambda: get_stock_chart(KR))
    check("stock_financials", lambda: get_financials(KR))
    check("stock_news", lambda: get_market_news(ticker=KR))
    check("stock_technical", lambda: technical_analysis(KR))

    from database import get_forecast_accuracy
    check("get_accuracy", lambda: get_forecast_accuracy(KR))

    print("=" * 90)
    n_err = sum(1 for _, s, _, _ in results if s == "ERROR")
    return 1 if n_err else 0

if __name__ == "__main__":
    sys.exit(main())
