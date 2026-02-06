"""
Market News Tool - Stock and market news retrieval
"""
import json
import yfinance as yf
from datetime import datetime
import pytz

# Ticker to Korean Company Name Mapping (for better search results)
TICKER_TO_NAME = {
    # Korean Stocks
    '005930.KS': '삼성전자',
    '000660.KS': 'SK하이닉스',
    '035420.KS': 'NAVER',
    '035720.KS': '카카오',
    '005380.KS': '현대차',
    '000270.KS': '기아',
    '051910.KS': 'LG화학',
    '006400.KS': '삼성SDI',
    '003670.KS': '포스코퓨처엠',
    '207940.KS': '삼성바이오로직스',
    '068270.KS': '셀트리온',
    '105560.KS': 'KB금융',
    '055550.KS': '신한지주',
    '066570.KS': 'LG전자',
    '012330.KS': '현대모비스',
    # US Stocks
    'AAPL': 'Apple',
    'MSFT': 'Microsoft',
    'GOOGL': 'Alphabet',
    'AMZN': 'Amazon',
    'NVDA': 'NVIDIA',
    'META': 'Meta',
    'TSLA': 'Tesla',
}

def get_company_name(ticker: str) -> str:
    """Get company name from ticker, or return ticker basename if not found."""
    return TICKER_TO_NAME.get(ticker, ticker.split('.')[0])


def get_market_news(ticker: str = None, query: str = None, limit: int = 10) -> str:
    """
    Get latest market news or news about a specific stock.
    Args:
        ticker: Stock ticker symbol (optional)
        query: Search query for general market news (optional)
        limit: Maximum number of news items to return
    Returns:
        JSON with news articles, headlines, and sources
    Raises:
        RuntimeError: If no news found (to trigger retry logic)
    """
    # Convert ticker to company name for better search
    search_name = get_company_name(ticker) if ticker else None
    print(f"📰 [News] Getting news for: {search_name or query or 'market'}")
    
    try:
        news_items = []
        
        if ticker:
            stock = yf.Ticker(ticker)
            news = stock.news[:limit] if hasattr(stock, 'news') else []
            
            for item in news:
                # Handle new yfinance structure (nested in 'content')
                content = item.get('content', item)
                
                # Extract fields with fallbacks
                title = content.get('title')
                
                # Provider/Publisher
                provider = content.get('provider', {})
                publisher = provider.get('displayName') if isinstance(provider, dict) else provider
                
                # Link
                click_url = content.get('clickThroughUrl')
                link = click_url.get('url') if isinstance(click_url, dict) else content.get('link')
                
                # Date
                pub_date = content.get('pubDate') or content.get('providerPublishTime')
                if pub_date:
                    try:
                        if isinstance(pub_date, (int, float)):
                            pub_date = datetime.fromtimestamp(pub_date).strftime("%Y-%m-%d %H:%M")
                    except:
                        pass
                
                # Thumbnail
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
                    "thumbnail": thumbnail
                })
        
        # If no ticker-specific news, use pygooglenews for general search
        if not news_items and query:
            # Use company name if query looks like a ticker
            if query in TICKER_TO_NAME:
                query = TICKER_TO_NAME[query]
            
            try:
                from pygooglenews import GoogleNews
                gn = GoogleNews(lang='ko', country='KR')
                search = gn.search(query)
                
                for entry in search.get('entries', [])[:limit]:
                    news_items.append({
                        "title": entry.get('title'),
                        "publisher": entry.get('source', {}).get('title'),
                        "link": entry.get('link'),
                        "published": entry.get('published'),
                        "type": "news",
                        "thumbnail": None
                    })
            except Exception as e:
                print(f"   ⚠️ GoogleNews search failed: {e}")
        
        # Raise exception if no news found (for retry logic)
        if not news_items:
            raise RuntimeError(f"No news found for '{search_name or query}'. Try a different search query.")
        
        return json.dumps({
            "status": "success",
            "ticker": ticker,
            "company_name": search_name,
            "query": query,
            "count": len(news_items),
            "news": news_items,
            "timestamp": datetime.now(pytz.timezone('Asia/Seoul')).isoformat()
        }, ensure_ascii=False)
        
    except RuntimeError:
        raise  # Re-raise RuntimeError for retry logic
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)})

