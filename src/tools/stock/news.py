"""
Market News Tool - Stock and market news retrieval with multi-language support

Note: English news for US stocks is passed directly to the Summarizer LLM,
which handles translation to Korean in the final analysis.
This avoids an extra LLM API call.
"""
import os
import json
import yfinance as yf
from datetime import datetime
from typing import Optional, List
import pytz

from market_utils import detect_market, get_company_name, get_english_name, TICKER_TO_NAME


from utils.response import ToolResponse

def get_market_news(ticker: str = None, query: str = None, limit: int = 10) -> str:
    """
    Get latest market news or news about a specific stock.
    Automatically detects market (KR/US) and optimizes search accordingly.
    
    Args:
        ticker: Stock ticker symbol (optional)
        query: Search query for general market news (optional)
        limit: Maximum number of news items to return
        
    Returns:
        Standardized JSON response
    """
    # Detect market and get appropriate company name
    market = detect_market(ticker) if ticker else 'KR'
    search_name = get_company_name(ticker) if ticker else None
    english_name = get_english_name(ticker) if ticker else None
    
    print(f"📰 [News] Getting news for: {search_name or query or 'market'} (Market: {market})")
    
    try:
        news_items = []
        
        # Step 1: Try yfinance news (works well for US stocks)
        if ticker:
            stock = yf.Ticker(ticker)
            news = stock.news[:limit] if hasattr(stock, 'news') else []
            
            for item in news:
                content = item.get('content', item)
                title = content.get('title')
                
                provider = content.get('provider', {})
                publisher = provider.get('displayName') if isinstance(provider, dict) else provider
                
                click_url = content.get('clickThroughUrl')
                link = click_url.get('url') if isinstance(click_url, dict) else content.get('link')
                
                pub_date = content.get('pubDate') or content.get('providerPublishTime')
                if pub_date:
                    try:
                        if isinstance(pub_date, (int, float)):
                            pub_date = datetime.fromtimestamp(pub_date).strftime("%Y-%m-%d %H:%M")
                    except:
                        pass
                
                thumb = content.get('thumbnail', {})
                thumbnail = None
                if isinstance(thumb, dict) and 'resolutions' in thumb:
                    res = thumb['resolutions']
                    if res and len(res) > 0:
                        thumbnail = res[0].get('url')
                
                news_items.append({
                    "title": title,
                    "publisher": publisher,
                    "link": link,
                    "published": pub_date,
                    "type": content.get('contentType', 'STORY'),
                    "thumbnail": thumbnail,
                    "language": "en" if market == "US" else "ko"
                })
        
        # Step 2: Google News search
        run_google_news = bool(query) or (not news_items and ticker)

        if run_google_news:
            effective_query = query
            if effective_query and effective_query in TICKER_TO_NAME:
                effective_query = TICKER_TO_NAME[effective_query]

            try:
                from pygooglenews import GoogleNews

                if market == 'US':
                    gn = GoogleNews(lang='en', country='US')
                    if effective_query and (english_name or search_name):
                        search_query = f"{english_name or search_name} {effective_query}"
                    elif effective_query:
                        search_query = f"{effective_query} stock"
                    else:
                        search_query = f"{english_name or ticker} stock"
                else:
                    gn = GoogleNews(lang='ko', country='KR')
                    if effective_query and search_name:
                        search_query = f"{search_name} {effective_query}"
                    else:
                        search_query = effective_query or search_name or ""

                print(f"   🔎 Google News search: '{search_query}'")
                search = gn.search(search_query) if search_query else {"entries": []}

                seen_titles = {(item.get("title") or "").strip().lower() for item in news_items}

                for entry in search.get('entries', [])[:limit]:
                    title = entry.get('title')
                    title_key = (title or "").strip().lower()
                    if not title or title_key in seen_titles:
                        continue
                    seen_titles.add(title_key)

                    news_items.append({
                        "title": title,
                        "publisher": entry.get('source', {}).get('title'),
                        "link": entry.get('link'),
                        "published": entry.get('published'),
                        "type": "news",
                        "thumbnail": None,
                        "language": "en" if market == "US" else "ko"
                    })
            except Exception as e:
                print(f"   ⚠️ GoogleNews search failed: {e}")

        # Keep the response size bounded
        if len(news_items) > limit:
            news_items = news_items[:limit]
        
        if not news_items:
            # Re-raise for retry logic compatibility if needed
            raise RuntimeError(f"No news found for '{search_name or query}'")
        
        return ToolResponse.success({
            "ticker": ticker,
            "company_name": search_name,
            "market": market,
            "query": query,
            "count": len(news_items),
            "news": news_items,
            "timestamp": datetime.now(pytz.timezone('Asia/Seoul')).isoformat()
        })
        
    except RuntimeError as re:
        raise re
    except Exception as e:
        return ToolResponse.error(str(e))


