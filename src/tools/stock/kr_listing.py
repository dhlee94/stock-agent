"""KR ticker resolver — deterministic name→ticker lookup against the KRX listing.

Hardcoded NAME_TO_TICKER maps cover only a handful of large caps; relying on the
LLM to infer tickers for the long tail produces hallucinations (e.g. 현대약품 →
041930.KS instead of the correct 004310.KS). This module pulls the full KRX
listing via FinanceDataReader once a day and provides an authoritative lookup.
"""
import os
from datetime import datetime, timedelta
from typing import Dict, Optional

import pandas as pd

_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "data"))
_CACHE_PATH = os.path.join(_DATA_DIR, "kr_listing.csv")
_CACHE_TTL = timedelta(hours=24)

_MEM_CACHE: Optional[pd.DataFrame] = None
_CODE_INDEX: Optional[Dict[str, str]] = None


def _market_suffix(market: str) -> str:
    m = (market or "").upper()
    if m == "KOSPI":
        return ".KS"
    if m == "KOSDAQ":
        return ".KQ"
    return ""


def load_kr_listing(force_refresh: bool = False) -> pd.DataFrame:
    """Return KRX listing with columns Code, Name, Market. Cached 24h on disk."""
    global _MEM_CACHE, _CODE_INDEX
    if _MEM_CACHE is not None and not force_refresh:
        return _MEM_CACHE
    _CODE_INDEX = None  # invalidate reverse index whenever the listing reloads

    stale = True
    if not force_refresh and os.path.exists(_CACHE_PATH):
        age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(_CACHE_PATH))
        stale = age > _CACHE_TTL

    if stale:
        import tempfile
        import FinanceDataReader as fdr
        df = fdr.StockListing("KRX")[["Code", "Name", "Market"]]
        os.makedirs(_DATA_DIR, exist_ok=True)
        # Atomic write: write to temp file then rename to avoid partial reads
        tmp_fd, tmp_path = tempfile.mkstemp(dir=_DATA_DIR, suffix=".csv")
        try:
            os.close(tmp_fd)
            df.to_csv(tmp_path, index=False)
            os.replace(tmp_path, _CACHE_PATH)
        except Exception:
            os.unlink(tmp_path)
            raise

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


def lookup_kr_name(ticker: str) -> Optional[str]:
    """Reverse lookup: a '<code>.KS' / '<code>.KQ' (or bare 6-digit code) → company
    name. Returns None when the code is unknown or the listing cannot be loaded.

    This is the authoritative ticker→name source for the KRX long tail. Without it,
    callers fall back to the bare code (e.g. '034020'), which then becomes a useless
    news search query and yields zero relevant articles."""
    if not ticker:
        return None
    code = ticker.split(".")[0].strip()
    if not code:
        return None
    global _CODE_INDEX
    if _CODE_INDEX is None:
        try:
            df = load_kr_listing()
        except Exception:
            return None
        _CODE_INDEX = {
            str(c).zfill(6): str(n)
            for c, n in zip(df["Code"], df["Name"])
            if pd.notna(c) and pd.notna(n)
        }
    return _CODE_INDEX.get(code.zfill(6))
