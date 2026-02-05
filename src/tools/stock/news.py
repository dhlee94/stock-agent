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
                news_items.append({
                    "title": item.get('title'),
                    "publisher": item.get('publisher'),
                    "link": item.get('link'),
                    "published": datetime.fromtimestamp(
                        item.get('providerPublishTime', 0)
                    ).strftime("%Y-%m-%d %H:%M") if item.get('providerPublishTime') else None,
                    "type": item.get('type'),
                    "thumbnail": item.get('thumbnail', {}).get('resolutions', [{}])[0].get('url') if item.get('thumbnail') else None
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
