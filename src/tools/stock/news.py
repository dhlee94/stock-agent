"""
Market News Tool — stock and market news retrieval.

Two sources are supported:
  - "yfinance" : Yahoo Finance news (+ Google News fallback). No API key.
                 Best for US tickers and global fallback.
  - "naver"    : Naver Open API news search. Korean coverage. Requires
                 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET.

`source="auto"` (default) routes KR tickers (.KS suffix or market=='KR') to
Naver when keys are configured, otherwise yfinance. US tickers go to yfinance.

English news for US stocks is passed directly to the Summarizer LLM, which
handles translation to Korean in the final analysis (no extra LLM call here).
"""
import os
import re
import html
import json
import yfinance as yf
from datetime import datetime
from typing import Optional, List, Dict, Tuple
import pytz

from .market_utils import detect_market, get_company_name, get_english_name, TICKER_TO_NAME
from utils.response import ToolResponse
from .news_naver import search_news as _naver_search, naver_keys_present
from .news_filter import filter_news


_VALID_SOURCES = {"auto", "naver", "yfinance"}
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text) -> Optional[str]:
    """Plain text from an HTML/RSS snippet (Google News summaries carry markup)."""
    if not text:
        return None
    s = html.unescape(_HTML_TAG_RE.sub("", str(text)))
    s = re.sub(r"\s+", " ", s).strip()  # collapse whitespace incl. &nbsp; (\xa0)
    return s or None


def _tag_and_rank_relevance(items: List[Dict], ticker: Optional[str],
                            search_name: Optional[str],
                            english_name: Optional[str]) -> Tuple[List[Dict], int]:
    """Tag each item 'direct' (names the subject) vs 'contextual' (domain/sector
    news that may still be relevant), then stable-sort direct-first.

    Nothing is dropped — a strict company-name filter would discard genuinely
    relevant domain articles (e.g. "광고요금제 스트리밍 트렌드" for Netflix). Tagging
    instead lets downstream weight direct vs contextual, and surfaces how many
    articles actually name the subject (the '관련 기사 3~4개뿐' signal)."""
    tokens = set()
    for t in (search_name, english_name):
        if t:
            tokens.add(t.lower())
    if ticker:
        tokens.add(ticker.lower())
        base = ticker.split(".")[0].lower()
        if base:
            tokens.add(base)

    direct = 0
    for it in items:
        hay = " ".join(str(v) for v in (it.get("title"), it.get("snippet")) if v).lower()
        is_direct = any(tok in hay for tok in tokens) if tokens else True
        it["relevance"] = "direct" if is_direct else "contextual"
        direct += is_direct
    items.sort(key=lambda x: 0 if x.get("relevance") == "direct" else 1)  # stable: keeps date order within tier
    return items, direct


def _resolve_source(source: str, market: str) -> str:
    """Pick the concrete source to use, honoring 'auto' and key availability."""
    source = (source or "auto").lower()
    if source not in _VALID_SOURCES:
        source = "auto"
    if source == "auto":
        return "naver" if (market == "KR" and naver_keys_present()) else "yfinance"
    if source == "naver" and not naver_keys_present():
        print("   ⚠️ Naver keys missing — falling back to yfinance")
        return "yfinance"
    return source


def _yfinance_news(ticker: Optional[str], query: Optional[str], limit: int, market: str,
                   search_name: Optional[str], english_name: Optional[str]) -> List[Dict]:
    """Existing logic: yfinance.Ticker.news + Google News fallback."""
    news_items: List[Dict] = []

    if ticker:
        stock = yf.Ticker(ticker)
        news = stock.news[:limit] if hasattr(stock, "news") else []
        for item in news:
            content = item.get("content", item)
            title = content.get("title")
            provider = content.get("provider", {})
            publisher = provider.get("displayName") if isinstance(provider, dict) else provider
            click_url = content.get("clickThroughUrl")
            link = click_url.get("url") if isinstance(click_url, dict) else content.get("link")
            pub_date = content.get("pubDate") or content.get("providerPublishTime")
            if pub_date and isinstance(pub_date, (int, float)):
                try:
                    pub_date = datetime.fromtimestamp(pub_date).strftime("%Y-%m-%d %H:%M")
                except Exception:
                    pass
            thumb = content.get("thumbnail", {})
            thumbnail = None
            if isinstance(thumb, dict) and "resolutions" in thumb:
                res = thumb["resolutions"]
                if res:
                    thumbnail = res[0].get("url")
            news_items.append({
                "title": title,
                "publisher": publisher,
                "link": link,
                "published": pub_date,
                "type": content.get("contentType", "STORY"),
                "thumbnail": thumbnail,
                "language": "en" if market == "US" else "ko",
                "snippet": _strip_html(content.get("summary") or content.get("description")),
            })

    run_google_news = bool(query) or (not news_items and ticker)
    if run_google_news:
        effective_query = query
        if effective_query and effective_query in TICKER_TO_NAME:
            effective_query = TICKER_TO_NAME[effective_query]
        try:
            from utils.google_news import GoogleNews
            if market == "US":
                gn = GoogleNews(lang="en", country="US")
                if effective_query and (english_name or search_name):
                    search_query = f"{english_name or search_name} {effective_query}"
                elif effective_query:
                    search_query = f"{effective_query} stock"
                else:
                    search_query = f"{english_name or ticker} stock"
            else:
                gn = GoogleNews(lang="ko", country="KR")
                if effective_query and search_name:
                    search_query = f"{search_name} {effective_query}"
                else:
                    search_query = effective_query or search_name or ""

            print(f"   🔎 Google News search: '{search_query}'")
            search = gn.search(search_query) if search_query else {"entries": []}
            seen_titles = {(item.get("title") or "").strip().lower() for item in news_items}
            for entry in search.get("entries", [])[:limit]:
                title = entry.get("title")
                title_key = (title or "").strip().lower()
                if not title or title_key in seen_titles:
                    continue
                seen_titles.add(title_key)
                news_items.append({
                    "title": title,
                    "publisher": entry.get("source", {}).get("title"),
                    "link": entry.get("link"),
                    "published": entry.get("published"),
                    "type": "news",
                    "thumbnail": None,
                    "language": "en" if market == "US" else "ko",
                    "snippet": _strip_html(entry.get("summary")),
                })
        except Exception as e:
            print(f"   ⚠️ GoogleNews search failed: {e}")

    return news_items


def _naver_news(ticker: Optional[str], query: Optional[str], limit: int,
                search_name: Optional[str]) -> List[Dict]:
    """Naver search: build a Korean query from company name + optional event keyword."""
    if query and search_name:
        q = f"{search_name} {query}"
    elif query:
        q = query
    elif search_name:
        q = f"{search_name} 주가"
    else:
        raise RuntimeError("Naver source requires ticker (for company name) or query")
    print(f"   🔎 Naver news search: '{q}'")
    return _naver_search(q, display=limit, sort="date")


def get_market_news(ticker: str = None, query: str = None, limit: int = 10,
                    source: str = "auto") -> str:
    """
    Get latest market or stock news. Dispatches across sources.

    Args:
        ticker: Stock ticker symbol (optional).
        query: Search query — name of event/term/topic (optional).
        limit: Max items returned (default 10).
        source: "auto" | "naver" | "yfinance".
                "auto" routes KR tickers to Naver (if keys present) and US to yfinance.

    Returns:
        Standardized JSON response with `source_used` recorded.
    """
    market = detect_market(ticker) if ticker else "KR"
    search_name = get_company_name(ticker) if ticker else None
    english_name = get_english_name(ticker) if ticker else None

    resolved = _resolve_source(source, market)
    print(f"📰 [News] {search_name or query or 'market'} (market={market}, source={source}→{resolved})")

    try:
        if resolved == "naver":
            news_items = _naver_news(ticker, query, limit, search_name)
        else:
            news_items = _yfinance_news(ticker, query, limit, market, search_name, english_name)

        # Drop ad / pump-and-dump spam before truncation so the kept items are the
        # real signal (filtering after [:limit] would waste slots on spam).
        news_items, dropped = filter_news(news_items)
        if dropped:
            print(f"   🧹 [News] 광고/스팸 {dropped}건 제외")

        # Tag relevance (direct vs contextual/domain) and rank direct-first so the
        # truncation below keeps subject-naming articles, while domain news survives
        # in the remaining slots.
        news_items, _ = _tag_and_rank_relevance(news_items, ticker, search_name, english_name)

        if len(news_items) > limit:
            news_items = news_items[:limit]
        if not news_items:
            raise RuntimeError(f"No news found for '{search_name or query}' via {resolved}")

        direct_count = sum(1 for it in news_items if it.get("relevance") == "direct")
        print(f"   🔎 [News] 관련성: direct {direct_count} / contextual {len(news_items) - direct_count}")

        return ToolResponse.success({
            "ticker": ticker,
            "company_name": search_name,
            "market": market,
            "query": query,
            "source_requested": source,
            "source_used": resolved,
            "count": len(news_items),
            "direct_count": direct_count,
            "contextual_count": len(news_items) - direct_count,
            "news": news_items,
            "timestamp": datetime.now(pytz.timezone("Asia/Seoul")).isoformat(),
        })

    except Exception as e:
        return ToolResponse.error(str(e))
