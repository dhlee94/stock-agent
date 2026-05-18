"""KR ticker resolver — deterministic name→ticker lookup against the KRX listing.

Hardcoded NAME_TO_TICKER maps cover only a handful of large caps; relying on the
LLM to infer tickers for the long tail produces hallucinations (e.g. 현대약품 →
041930.KS instead of the correct 004310.KS). This module pulls the full KRX
listing via FinanceDataReader once a day and provides an authoritative lookup.
"""
import os
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "data"))
_CACHE_PATH = os.path.join(_DATA_DIR, "kr_listing.csv")
_CACHE_TTL = timedelta(hours=24)

_MEM_CACHE: Optional[pd.DataFrame] = None


def _market_suffix(market: str) -> str:
    m = (market or "").upper()
    if m == "KOSPI":
        return ".KS"
    if m == "KOSDAQ":
        return ".KQ"
    return ""


def load_kr_listing(force_refresh: bool = False) -> pd.DataFrame:
    """Return KRX listing with columns Code, Name, Market. Cached 24h on disk."""
    global _MEM_CACHE
    if _MEM_CACHE is not None and not force_refresh:
        return _MEM_CACHE

    stale = True
    if not force_refresh and os.path.exists(_CACHE_PATH):
        age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(_CACHE_PATH))
        stale = age > _CACHE_TTL

    if stale:
        import FinanceDataReader as fdr
        df = fdr.StockListing("KRX")[["Code", "Name", "Market"]]
        os.makedirs(_DATA_DIR, exist_ok=True)
        df.to_csv(_CACHE_PATH, index=False)

    _MEM_CACHE = pd.read_csv(_CACHE_PATH, dtype={"Code": str})
    return _MEM_CACHE


def lookup_kr_ticker(name: str) -> Optional[str]:
    """Exact-match a Korean company name. Returns '<code>.KS' / '<code>.KQ' or None."""
    if not name:
        return None
    df = load_kr_listing()
    row = df[df["Name"] == name.strip()]
    if row.empty:
        return None
    r = row.iloc[0]
    suffix = _market_suffix(r["Market"])
    if not suffix:
        return None
    return f"{r['Code']}{suffix}"
