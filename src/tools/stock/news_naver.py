"""
Naver Open API — News Search adapter.

Free tier: 25,000 requests / day / app. Requires NAVER_CLIENT_ID and
NAVER_CLIENT_SECRET in env (get them at https://developers.naver.com/apps).

Output items are normalized to the same shape as the yfinance / Google News
path used elsewhere in this codebase, so callers can treat sources
interchangeably.
"""
import os
import re
import sys
import html
import urllib.parse
import urllib.request
import json
from typing import Optional, List, Dict

# Make sure src/ is importable when this module is loaded standalone.
_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.dirname(os.path.dirname(_HERE))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from config import NAVER_CLIENT_ID, NAVER_CLIENT_SECRET


NAVER_NEWS_ENDPOINT = "https://openapi.naver.com/v1/search/news.json"
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def naver_keys_present() -> bool:
    return bool(NAVER_CLIENT_ID) and bool(NAVER_CLIENT_SECRET)


def _strip_html(text: Optional[str]) -> Optional[str]:
    if not text:
        return text
    return html.unescape(_HTML_TAG_RE.sub("", text)).strip()


def search_news(query: str, display: int = 10, sort: str = "date") -> List[Dict]:
    """
    Call Naver news search. Returns a list of normalized news items.
    Raises RuntimeError when keys are missing or the API call fails — callers
    decide whether to fall back to another source.

    Args:
        query: Search query (Korean recommended for KR coverage).
        display: 1..100, number of items to return.
        sort: "date" (newest first) or "sim" (relevance).
    """
    if not naver_keys_present():
        raise RuntimeError("Naver API keys not configured (NAVER_CLIENT_ID / NAVER_CLIENT_SECRET)")
    if not query:
        raise RuntimeError("Naver news search requires a non-empty query")

    display = max(1, min(int(display), 100))
    params = urllib.parse.urlencode({"query": query, "display": display, "sort": sort})
    url = f"{NAVER_NEWS_ENDPOINT}?{params}"

    req = urllib.request.Request(url)
    req.add_header("X-Naver-Client-Id", NAVER_CLIENT_ID)
    req.add_header("X-Naver-Client-Secret", NAVER_CLIENT_SECRET)

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
    except Exception as e:
        raise RuntimeError(f"Naver API call failed: {e}") from e

    data = json.loads(raw)
    items = data.get("items", []) or []

    normalized: List[Dict] = []
    for item in items:
        normalized.append({
            "title": _strip_html(item.get("title")),
            "publisher": None,  # Naver search does not expose publisher reliably
            "link": item.get("originallink") or item.get("link"),
            "published": item.get("pubDate"),  # RFC1123 string, e.g. "Mon, 26 Aug 2024 14:35:00 +0900"
            "type": "news",
            "thumbnail": None,
            "language": "ko",
            "snippet": _strip_html(item.get("description")),
        })
    return normalized
