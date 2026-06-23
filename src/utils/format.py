"""Deterministic money/number formatting for tool outputs.

LLMs reliably MIS-convert raw integers into human units — Korean 억(10^8)/조(10^12)
grouping especially, since Korean groups by 10^4 (만·억·조) while the model is
biased to the 10^3 (K/M/B) grouping of English. Every 100×/1000× "unit error" in
the analysis came from the narrator LLM, never the tools (the raw values are
correct). So tools format aggregates HERE and the prompts copy the string verbatim
instead of recomputing units — the same "derive in code, don't let the LLM guess"
rule already applied to company names and support/resistance levels.
"""
from typing import Iterable, Optional


def _is_us(market: str) -> bool:
    return (market or "").strip().upper() == "US"


def _num(value) -> Optional[float]:
    if value is None:
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return None if n != n else n  # drop NaN


def format_money(value, market: str = "KR", *, per_share: bool = False) -> Optional[str]:
    """Human-readable money string for a raw numeric value, market-aware.

    Aggregates (market cap, FCF, cash, debt, revenue, EV): Korean 조/억 for KRW,
    T/B/M for USD. Per-share / price values (price, EPS, target, dividend): thousands
    -grouped with the currency symbol. Returns None for None/NaN so the caller can
    omit the `*_display` field entirely.

        format_money(1_244_509_110_272, "KR")            -> "1.24조원"
        format_money(282_377_000_000, "KR")              -> "2,824억원"
        format_money(-985_304_858_624, "KR")             -> "-9,853억원"
        format_money(967_000, "KR", per_share=True)      -> "967,000원"
        format_money(34_804_944_863_232, "US")           -> "$34.80T"
        format_money(717_657_867_020, "US")              -> "$717.66B"
        format_money(80.5, "US", per_share=True)         -> "$80.50"
    """
    n = _num(value)
    if n is None:
        return None
    us = _is_us(market)
    sign = "-" if n < 0 else ""
    a = abs(n)

    if per_share:
        return f"{sign}${a:,.2f}" if us else f"{sign}{a:,.0f}원"

    if us:
        if a >= 1e12:
            return f"{sign}${a / 1e12:.2f}T"
        if a >= 1e9:
            return f"{sign}${a / 1e9:.2f}B"
        if a >= 1e6:
            return f"{sign}${a / 1e6:.2f}M"
        return f"{sign}${a:,.0f}"

    # KRW: group by the Korean myriad units 조(10^12) / 억(10^8)
    if a >= 1e12:
        return f"{sign}{a / 1e12:.2f}조원"
    if a >= 1e8:
        return f"{sign}{a / 1e8:,.0f}억원"
    return f"{sign}{a:,.0f}원"


def attach_money_display(section: dict, market: str = "KR", *,
                         agg_keys: Iterable[str] = (),
                         per_share_keys: Iterable[str] = ()) -> dict:
    """In-place: for each money key present in `section`, add a sibling
    `<key>_display` with the formatted string. Only whitelisted keys are touched
    (ratios like PER/ROE and dates must NOT be money-formatted). Returns `section`.
    """
    if not isinstance(section, dict):
        return section
    for k in agg_keys:
        if k in section:
            disp = format_money(section.get(k), market)
            if disp is not None:
                section[f"{k}_display"] = disp
    for k in per_share_keys:
        if k in section:
            disp = format_money(section.get(k), market, per_share=True)
            if disp is not None:
                section[f"{k}_display"] = disp
    return section
