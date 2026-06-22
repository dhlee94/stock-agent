"""US ticker resolver — name→ticker lookup using FDR's NASDAQ/NYSE/AMEX listings.

Backs up the curated NAME_TO_TICKER (Korean phonetic aliases) for long-tail US
symbols. Resolution tries exact symbol → exact name → normalized name (corporate
suffixes stripped, non-alphanumerics dropped), so 'Netflix', 'Netflix Inc', and
'netflix' all collapse to the same key.
"""
import os
import re
from datetime import datetime, timedelta
from typing import Dict, Optional

import pandas as pd

_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "data"))
_CACHE_PATH = os.path.join(_DATA_DIR, "us_listing.csv")
_CACHE_TTL = timedelta(hours=24)

_MEM_CACHE: Optional[pd.DataFrame] = None
_NAME_INDEX: Optional[Dict[str, str]] = None
_SYMBOL_INDEX: Optional[Dict[str, str]] = None

_CORP_SUFFIXES = (
    " incorporated", " corporation", " holdings", " holding", " companies",
    " company", " group", " limited", " inc", " corp", " ltd", " plc",
    " co", " adr", " class a", " class b", " class c",
)


def _normalize(name: str) -> str:
    n = name.strip().lower()
    changed = True
    while changed:
        changed = False
        for suf in _CORP_SUFFIXES:
            if n.endswith(suf):
                n = n[: -len(suf)].rstrip(" ,.")
                changed = True
    return re.sub(r"[^a-z0-9]+", "", n)


def load_us_listing(force_refresh: bool = False) -> pd.DataFrame:
    """Return combined US listing with columns Symbol, Name. Cached 24h on disk."""
    global _MEM_CACHE, _NAME_INDEX, _SYMBOL_INDEX
    if _MEM_CACHE is not None and not force_refresh:
        return _MEM_CACHE

    stale = True
    if not force_refresh and os.path.exists(_CACHE_PATH):
        age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(_CACHE_PATH))
        stale = age > _CACHE_TTL

    if stale:
        import FinanceDataReader as fdr
        frames = []
        for ex in ("NASDAQ", "NYSE", "AMEX"):
            try:
                frames.append(fdr.StockListing(ex)[["Symbol", "Name"]])
            except Exception as e:
                print(f"[us_listing] {ex} fetch failed: {e}")
        if not frames:
            raise RuntimeError("All US listing fetches failed")
        combined = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["Symbol"])
        os.makedirs(_DATA_DIR, exist_ok=True)
        combined.to_csv(_CACHE_PATH, index=False)

    _MEM_CACHE = pd.read_csv(_CACHE_PATH)
    _NAME_INDEX = None
    _SYMBOL_INDEX = None
    return _MEM_CACHE


def _name_index() -> Dict[str, str]:
    global _NAME_INDEX
    if _NAME_INDEX is not None:
        return _NAME_INDEX
    df = load_us_listing()
    idx: Dict[str, str] = {}
    for sym, name in zip(df["Symbol"], df["Name"]):
        if pd.isna(sym) or pd.isna(name):
            continue
        norm = _normalize(str(name))
        if norm and norm not in idx:
            idx[norm] = str(sym)
    _NAME_INDEX = idx
    return idx


def lookup_us_ticker(name: str) -> Optional[str]:
    """Resolve a US company name (or symbol) to its ticker. None if unresolvable."""
    if not name:
        return None
    s = name.strip()
    if not s:
        return None
    df = load_us_listing()
    if re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,5}", s) and (df["Symbol"] == s).any():
        return s
    norm = _normalize(s)
    if not norm:
        return None
    return _name_index().get(norm)


def lookup_us_name(symbol: str) -> Optional[str]:
    """Reverse lookup: a US symbol → its listed company name. None if unknown or the
    listing cannot be loaded. Mirrors lookup_kr_name for the US long tail."""
    if not symbol:
        return None
    s = symbol.strip().upper()
    if not s:
        return None
    global _SYMBOL_INDEX
    if _SYMBOL_INDEX is None:
        try:
            df = load_us_listing()
        except Exception:
            return None
        _SYMBOL_INDEX = {
            str(sym).upper(): str(name)
            for sym, name in zip(df["Symbol"], df["Name"])
            if pd.notna(sym) and pd.notna(name)
        }
    return _SYMBOL_INDEX.get(s)


def is_valid_us_ticker(symbol: str) -> bool:
    if not symbol:
        return False
    df = load_us_listing()
    return bool((df["Symbol"] == symbol).any())
