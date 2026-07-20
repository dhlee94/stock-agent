"""
Reproduction test — cross-subtask current-price inconsistency.

During extended hours (marketState PRE/POST) yfinance freezes info.currentPrice /
regularMarketPrice at the prior regular-session close while the live print lives
in info.preMarketPrice / postMarketPrice. Only `stock_price` was taught this
(commit 8fafb3f); `stock_dcf`, `stock_financials`, and _market_consistency_anchor
each still re-derive "current price" from currentPrice/regularMarketPrice on their
own. So one report carries several different current prices for the SAME stock,
and — worse — every deterministic upside/undervaluation field that feeds the
triangulated valuation (DCF in_buy_zone / upside_vs_fair, consensus upside,
relative P/E) is anchored to the STALE price while the [현재 상황] header shows the
LIVE one. The triangulation conclusion is silently wrong by the extended-hours gap.

These tests assert the invariant we WANT (all tools agree on one live current
price, and every upside % is measured against it). They therefore FAIL until the
shared resolve_current_price() fix lands — they are the red-before-green repro.

Run inside the app image (needs pandas/yfinance/pytz):
    docker exec stock-agent-app python -m pytest tests/test_price_consistency.py -v
or as a plain demonstration:
    docker exec stock-agent-app python tests/test_price_consistency.py
"""
import json
import os
import re
import sys

try:
    import pytest
except ModuleNotFoundError:  # allow the __main__ demonstration to run without pytest
    pytest = None

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

TICKER = "NFLX"

# --- Simulated extended-hours (PRE) snapshot ------------------------------------
# The $74-vs-$68 earnings-gap scenario from the memory: regular close frozen high,
# pre-market print live and lower.
REGULAR_CLOSE = 74.35   # frozen regular-session close — STALE during PRE
PRE_MARKET = 67.30      # live pre-market print — what brokers/Google show
PREV_CLOSE = 73.00
SHARES = 430_000_000
MARKET_CAP = int(round(REGULAR_CLOSE * SHARES))  # keep price×shares==mktcap so the DCF share-count check is silent
TARGET_MEAN = 90.00

FAKE_INFO = {
    "marketState": "PRE",
    "regularMarketPrice": REGULAR_CLOSE,
    "currentPrice": REGULAR_CLOSE,          # yfinance freezes currentPrice at the regular close during PRE
    "preMarketPrice": PRE_MARKET,
    "regularMarketPreviousClose": PREV_CLOSE,
    "previousClose": PREV_CLOSE,
    "sharesOutstanding": SHARES,
    "marketCap": MARKET_CAP,
    "fiftyTwoWeekLow": 60.0,
    "fiftyTwoWeekHigh": 95.0,
    "regularMarketDayHigh": 75.0,
    "regularMarketDayLow": 73.5,
    "regularMarketVolume": 1_000_000,
    "beta": 1.35,
    "revenueGrowth": 0.12,
    "freeCashflow": 3_000_000_000,
    "operatingCashflow": 4_000_000_000,
    "totalDebt": 1_000_000_000,
    "totalCash": 2_000_000_000,
    "targetMeanPrice": TARGET_MEAN,
    "targetHighPrice": 110.0,
    "targetLowPrice": 70.0,
    "targetMedianPrice": 92.0,
    "recommendationMean": 2.0,
    "recommendationKey": "buy",
    "numberOfAnalystOpinions": 40,
    "trailingPE": 30.0,
    "forwardPE": 25.0,
    "priceToSalesTrailing12Months": 6.0,
    "shortName": "Netflix Inc",
    "longName": "Netflix, Inc.",
    "currency": "USD",
}


class _FakeTicker:
    def __init__(self, ticker, *a, **k):
        self.ticker = ticker

    @property
    def info(self):
        return dict(FAKE_INFO)

    @property
    def cashflow(self):
        # Force _reliable_fcf onto info.freeCashflow and growth onto revenueGrowth,
        # so the DCF runs without a cash-flow statement.
        return None

    financials = None
    balance_sheet = None

    def history(self, *a, **k):
        import pandas as pd
        idx = pd.date_range(end="2026-07-20", periods=5, freq="D")
        return pd.DataFrame(
            {
                "Close": [70.0, 71.0, 72.0, 73.0, REGULAR_CLOSE],
                "High": [71.0, 72.0, 73.0, 74.0, 75.0],
                "Low": [69.0, 70.0, 71.0, 72.0, 73.5],
                "Volume": [1_000_000] * 5,
            },
            index=idx,
        )


def _install_fake():
    import yfinance
    yfinance.Ticker = _FakeTicker


if pytest is not None:
    @pytest.fixture(autouse=True)
    def _patch_yf(monkeypatch):
        import yfinance
        monkeypatch.setattr(yfinance, "Ticker", _FakeTicker)


# --- helpers --------------------------------------------------------------------

def _price_current():
    from tools.stock.price import get_stock_price
    return json.loads(get_stock_price(TICKER, "US"))["current_price"]


def _dcf():
    from tools.stock.dcf import get_dcf
    return json.loads(get_dcf(TICKER, "US"))


def _financials_analyst():
    from tools.stock.financials import get_financials
    return json.loads(get_financials(TICKER))["analyst"]


def _anchor_price():
    from agent_client import _market_consistency_anchor
    text = _market_consistency_anchor(TICKER)
    m = re.search(r"current price \$([\d,]+\.?\d*)", text)
    return float(m.group(1).replace(",", "")) if m else None


# --- tests ----------------------------------------------------------------------

def test_current_price_consistent_across_tools():
    """Every tool must report the SAME live current price for one stock."""
    prices = {
        "stock_price": _price_current(),
        "stock_dcf": _dcf()["current_price"],
        "stock_financials": _financials_analyst()["current_price"],
        "market_anchor": _anchor_price(),
    }
    # stock_price is the source of truth (marketState-aware); all others must match it.
    live = prices["stock_price"]
    assert live == pytest.approx(PRE_MARKET, abs=0.01), prices
    mismatched = {k: v for k, v in prices.items() if v != pytest.approx(live, abs=0.01)}
    assert not mismatched, (
        f"tools disagree on current price (live={live}): {prices} — "
        f"stale-anchored: {mismatched}"
    )


def test_consensus_upside_anchored_to_live_price():
    """The consensus 상승여력 the summarizer cites must be measured vs the live price."""
    analyst = _financials_analyst()
    live = _price_current()
    expected = round((TARGET_MEAN - live) / live * 100, 2)
    assert analyst["upside_to_mean_target_pct"] == pytest.approx(expected, abs=0.1), (
        f"consensus upside {analyst['upside_to_mean_target_pct']}% is anchored to the "
        f"stale ${analyst['current_price']} close, not the live ${live} price "
        f"(should be {expected}%)"
    )


def test_dcf_valuation_anchored_to_live_price():
    """DCF current_price / in_buy_zone / upside must be measured vs the live price."""
    dcf = _dcf()
    live = _price_current()
    assert dcf["current_price"] == pytest.approx(live, abs=0.01), (
        f"DCF anchors to ${dcf['current_price']} (stale close) not ${live} (live) — "
        f"in_buy_zone={dcf['in_buy_zone']}, upside_vs_fair={dcf['upside_vs_fair_pct']}% "
        f"are all computed off the wrong price"
    )
    expected_upside = round((dcf["fair_value"] - live) / live * 100, 2)
    assert dcf["upside_vs_fair_pct"] == pytest.approx(expected_upside, abs=0.1)


if __name__ == "__main__":
    # Plain demonstration (no pytest) — prints the divergence table.
    _install_fake()
    live = _price_current()
    dcf = _dcf()
    analyst = _financials_analyst()
    anchor = _anchor_price()
    print("\n=== Cross-subtask current-price divergence (marketState=PRE) ===")
    print(f"  live pre-market print           : ${PRE_MARKET:.2f}")
    print(f"  frozen regular close (stale)    : ${REGULAR_CLOSE:.2f}\n")
    print(f"  stock_price.current_price       : ${live:.2f}")
    print(f"  stock_dcf.current_price         : ${dcf['current_price']:.2f}")
    print(f"  stock_financials.current_price  : ${analyst['current_price']:.2f}")
    print(f"  market_anchor current price     : ${anchor:.2f}")
    print("\n  --- downstream triangulation damage ---")
    print(f"  consensus upside (reported)     : {analyst['upside_to_mean_target_pct']}%")
    print(f"  consensus upside (vs live)      : {round((TARGET_MEAN - live) / live * 100, 2)}%")
    print(f"  DCF fair_value                  : ${dcf['fair_value']:.2f}")
    print(f"  DCF upside_vs_fair (reported)   : {dcf['upside_vs_fair_pct']}%")
    print(f"  DCF upside_vs_fair (vs live)    : {round((dcf['fair_value'] - live) / live * 100, 2)}%")
    print(f"  DCF in_buy_zone (reported)      : {dcf['in_buy_zone']}")
    print(f"  DCF buy_below_price             : ${dcf['buy_below_price']:.2f}")
    print(f"  in_buy_zone if measured vs live : {live <= dcf['buy_below_price']}")
