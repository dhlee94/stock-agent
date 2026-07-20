"""
Regression test — round-by-round DCF growth-assumption consistency.

The MCP tool stock_dcf exposes a growth_override, and the Tier-2 integration slot
deliberately re-runs the DCF with a "catalyst-informed" override. Previously an
override REPLACED the base case, so the same stock showed a different intrinsic
value / fair_value across rounds (override vs no-override) and the Reflector read
the two as a contradiction.

The fix: headline DCF fields (intrinsic_value, fair_value, buy_below_price, upside,
in_buy_zone) are ALWAYS data-derived and identical for a ticker regardless of any
override; a growth_override only ADDS a labeled `override_scenario` what-if block.

These tests assert that invariant. Run inside the app image:
    docker exec stock-agent-app python -m pytest tests/test_dcf_round_consistency.py -v
"""
import json
import os
import sys

try:
    import pytest
except ModuleNotFoundError:
    pytest = None

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

TICKER = "NFLX"
PRICE = 70.0
SHARES = 430_000_000

FAKE_INFO = {
    "marketState": "REGULAR",
    "regularMarketPrice": PRICE,
    "currentPrice": PRICE,
    "sharesOutstanding": SHARES,
    "marketCap": int(round(PRICE * SHARES)),
    "beta": 1.35,
    "revenueGrowth": 0.12,
    "freeCashflow": 3_000_000_000,
    "operatingCashflow": 4_000_000_000,
    "totalDebt": 1_000_000_000,
    "totalCash": 2_000_000_000,
    "fiftyTwoWeekLow": 55.0,
    "fiftyTwoWeekHigh": 95.0,
    "shortName": "Netflix Inc",
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
        return None  # force FCF onto info.freeCashflow, growth onto revenueGrowth

    financials = None
    balance_sheet = None


def _install_fake():
    import yfinance
    yfinance.Ticker = _FakeTicker


if pytest is not None:
    @pytest.fixture(autouse=True)
    def _patch_yf(monkeypatch):
        import yfinance
        monkeypatch.setattr(yfinance, "Ticker", _FakeTicker)


def _dcf(**kwargs):
    from tools.stock.dcf import get_dcf
    return json.loads(get_dcf(TICKER, "US", **kwargs))


HEADLINE_KEYS = (
    "intrinsic_value", "fair_value", "buy_below_price",
    "upside_vs_fair_pct", "upside_vs_base_pct", "in_buy_zone",
    "margin_of_safety_pct", "current_price",
)


def test_headline_identical_regardless_of_override():
    """No-override and override runs must agree on every canonical headline field."""
    base = _dcf()                      # round 1: data-derived
    override = _dcf(growth_override=0.20)  # round 2: Tier-2 catalyst re-run
    for k in HEADLINE_KEYS:
        assert base[k] == override[k], (
            f"DCF headline '{k}' changed with an override "
            f"({base[k]} → {override[k]}) — the canonical valuation must be "
            f"identical across rounds"
        )


def test_override_appears_only_as_labeled_scenario():
    """The override lives in override_scenario, not in the headline."""
    base = _dcf()
    override = _dcf(growth_override=0.20)
    assert base["override_scenario"] is None
    sc = override["override_scenario"]
    assert sc is not None
    assert sc["growth_override_pct"] == 20.0
    # The scenario is a genuinely different valuation (20% > data-derived 12%),
    # proving the override still does something — just not to the headline.
    assert sc["fair_value"] != override["fair_value"]


def test_repeated_calls_are_deterministic():
    """Same inputs → byte-identical output (no per-round drift)."""
    from tools.stock.dcf import get_dcf
    a = get_dcf(TICKER, "US")
    b = get_dcf(TICKER, "US")
    assert a == b


if __name__ == "__main__":
    _install_fake()
    base = _dcf()
    override = _dcf(growth_override=0.20)
    print("\n=== DCF round-consistency (data growth 12% vs override 20%) ===")
    print(f"  headline fair_value  no-override : ${base['fair_value']}")
    print(f"  headline fair_value  +override   : ${override['fair_value']}")
    print(f"  headline identical               : "
          f"{all(base[k] == override[k] for k in HEADLINE_KEYS)}")
    print(f"  base.override_scenario           : {base['override_scenario']}")
    sc = override["override_scenario"]
    print(f"  override_scenario.fair_value     : ${sc['fair_value']} (override={sc['growth_override_pct']}%)")
    print(f"  override_scenario.note           : {sc['note']}")
