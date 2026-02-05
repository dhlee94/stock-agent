"""
Market News Tool - Stock and market news retrieval
"""
import json
import yfinance as yf
from datetime import datetime
import pytz


def get_market_news(ticker: str = None, query: str = None, limit: int = 10) -> str:
    """
    Get latest market news or news about a specific stock.
    Args:
        ticker: Stock ticker symbol (optional)
        query: Search query for general market news (optional)
        limit: Maximum number of news items to return
    Returns:
        JSON with news articles, headlines, and sources
    """
    print(f"📰 [News] Getting news for: {ticker or query or 'market'}")
    
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
                        # If simple string format, leave as is, otherwise try parsing
                        if isinstance(pub_date, (int, float)):
                            pub_date = datetime.fromtimestamp(pub_date).strftime("%Y-%m-%d %H:%M")
                        # If ISO format string, simplistic handling or leave as is
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
            except Exception:
                pass
        
        return json.dumps({
            "status": "success",
            "ticker": ticker,
            "query": query,
            "count": len(news_items),
            "news": news_items,
            "timestamp": datetime.now(pytz.timezone('Asia/Seoul')).isoformat()
        }, ensure_ascii=False)
        
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)})
