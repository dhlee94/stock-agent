"""
Deterministic ad / pump-and-dump spam filter for fetched news headlines.

Two easy places to tune what gets filtered:
  1. Edit AD_SPAM_MARKERS below (the curated, version-controlled default).
  2. WITHOUT touching code — add markers (one per line, '#' for comments) to
     data/news_spam_markers.txt; they are merged with the built-ins at import.

Precision-first: include only markers that virtually never appear in legitimate
financial journalism. Plain words like "추천"/"수익률" are intentionally NOT here
— they show up in real headlines ("증권사 매수 추천", "수익률 회복"), so matching
them would drop genuine news. When in doubt, leave it out: over-dropping real
coverage is worse than letting a borderline item through (a thin-coverage
guardrail downstream already hedges low article counts).
"""
import os
from typing import Dict, List, Tuple

# ── Edit here ───────────────────────────────────────────────────────────────
AD_SPAM_MARKERS: List[str] = [
    # KR — 리딩방 / 종목추천 / 컨택 유도 (정상 기사엔 거의 안 나오는 고확신 마커)
    "[광고]", "(광고)", "리딩방", "주식리딩", "오픈채팅", "카톡방",
    "텔레그램방", "vip방", "무료추천", "수익률 보장", "원금보장",
    "급등주 공개", "종목 추천 받",
    # EN — sponsored / promo
    "sponsored", "[ad]", "advertisement", "promoted", "guaranteed return",
]
# ─────────────────────────────────────────────────────────────────────────────

_HERE = os.path.dirname(os.path.abspath(__file__))                # src/tools/stock
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))  # repo root
_EXTRA_MARKERS_FILE = os.path.join(_ROOT, "data", "news_spam_markers.txt")


def _load_markers() -> List[str]:
    """Built-in markers + optional user additions from the data/ text file."""
    markers = [m.lower() for m in AD_SPAM_MARKERS]
    try:
        with open(_EXTRA_MARKERS_FILE, encoding="utf-8") as f:
            for line in f:
                term = line.split("#", 1)[0].strip()  # allow inline/full-line comments
                if term:
                    markers.append(term.lower())
    except FileNotFoundError:
        pass  # no user file — defaults only
    except Exception as e:
        print(f"   ⚠️ [News] spam-marker file unreadable ({_EXTRA_MARKERS_FILE}): {e}")
    return markers


_MARKERS = _load_markers()


def is_ad_or_spam(item: Dict) -> bool:
    """True if a news item looks like an ad / pump-and-dump spam.

    Matches high-confidence markers against title + snippet + publisher,
    case-insensitively. Empty/featureless items are kept (return False)."""
    haystack = " ".join(
        str(v) for v in (item.get("title"), item.get("snippet"), item.get("publisher")) if v
    ).lower()
    if not haystack.strip():
        return False
    return any(m in haystack for m in _MARKERS)


def filter_news(items: List[Dict]) -> Tuple[List[Dict], int]:
    """Drop ad/spam items. Returns (kept_items, dropped_count)."""
    kept = [it for it in items if not is_ad_or_spam(it)]
    return kept, len(items) - len(kept)
