"""Unit tests for DriverMemory's ticker→name invariant.

The stored name must always be derived from the ticker (exchange listing),
never from the LLM-supplied caller name. Regression guard for the bug where
S-Oil (010950.KS) data got persisted under "SK Innovation" because save_drivers
trusted the caller-supplied name.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "tools", "stock"))

import database  # noqa: E402
from driver_memory import DriverMemory, get_company_name  # noqa: E402


def test_resolver_is_authoritative():
    # Exchange listing / curated map is the source of truth, not any caller claim.
    assert get_company_name("010950.KS") == "S-Oil"
    assert get_company_name("096770.KS") == "SK이노베이션"
    # Unknown ticker falls back to the bare code (never crashes).
    assert get_company_name("999999.KS") == "999999"


def test_save_drivers_ignores_caller_name(monkeypatch):
    """The caller lies (SK Innovation for S-Oil's ticker); we store S-Oil."""
    saved = []
    monkeypatch.setattr(database, "get_ticker_info", lambda t: {"ticker": t})
    monkeypatch.setattr(database, "add_ticker", lambda *a, **k: None)
    monkeypatch.setattr(database, "add_driver", lambda **k: saved.append(k) or 1)

    DriverMemory().save_drivers("010950.KS", "SK Innovation", ["정제마진"], [])

    assert saved, "expected a driver row to be written"
    assert all(row["name"] == "S-Oil" for row in saved)
    assert all(row["ticker"] == "010950.KS" for row in saved)


def test_save_drivers_registers_unknown_ticker_with_canonical_name(monkeypatch):
    """A ticker not yet in `tickers` is registered under its canonical name+market."""
    added = {}
    monkeypatch.setattr(database, "get_ticker_info", lambda t: None)
    monkeypatch.setattr(
        database, "add_ticker",
        lambda ticker, name, sector, market: added.update(
            ticker=ticker, name=name, market=market),
    )
    monkeypatch.setattr(database, "add_driver", lambda **k: 1)

    DriverMemory().save_drivers("010950.KS", "WRONG NAME", ["x"], [])

    assert added["name"] == "S-Oil"
    assert added["market"] == "KR"
