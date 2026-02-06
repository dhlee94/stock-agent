"""
Market News Tool - Stock and market news retrieval with multi-language support
"""
import os
import json
import yfinance as yf
from datetime import datetime
from typing import Optional, List
import pytz

from market_utils import detect_market, get_company_name, get_english_name, TICKER_TO_NAME

# LLM configuration
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "gemini").lower()
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")


def _summarize_english_news_to_korean(news_titles: List[str], company_name: str) -> str:
    """
    Summarize English news headlines into Korean using LLM.
    
    Args:
        news_titles: List of English news headlines
        company_name: Company name for context
        
    Returns:
        Korean summary (3 sentences)
    """
    if not news_titles:
        return ""
    
    headlines = "\n".join([f"- {title}" for title in news_titles[:10]])
    
    prompt = f"""You are a global financial analyst. Summarize the following English news headlines about {company_name} into 3 concise Korean sentences.

IMPORTANT RULES:
1. Focus on the impact on stock price
2. Keep key technical terms and proper nouns in their ORIGINAL ENGLISH form alongside Korean
   Example: "Blackwell 칩 출시로 인한 수요 증가" NOT "블랙웰 칩..."
3. Include specific figures if mentioned (revenue, %, etc.)

News Headlines:
{headlines}

Write ONLY 3 Korean sentences, nothing else:"""

    try:
        if LLM_PROVIDER == "groq" and GROQ_API_KEY:
            from groq import Groq
            client = Groq(api_key=GROQ_API_KEY)
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=300
            )
            return response.choices[0].message.content.strip()
        else:
            import google.generativeai as genai
            GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
            if GEMINI_API_KEY:
                genai.configure(api_key=GEMINI_API_KEY)
                model = genai.GenerativeModel("gemini-2.0-flash")
                response = model.generate_content(prompt)
                return response.text.strip()
    except Exception as e:
        print(f"   ⚠️ LLM summarization failed: {e}")
    
    return ""


def get_market_news(ticker: str = None, query: str = None, limit: int = 10, 
                    summarize_for_korean: bool = True) -> str:
    """
    Get latest market news or news about a specific stock.
    Automatically detects market (KR/US) and optimizes search accordingly.
    
    Args:
        ticker: Stock ticker symbol (optional)
        query: Search query for general market news (optional)
        limit: Maximum number of news items to return
        summarize_for_korean: If True, summarize US news to Korean
        
    Returns:
        JSON with news articles, headlines, and optional Korean summary for US stocks
        
    Raises:
        RuntimeError: If no news found (to trigger retry logic)
    """
    # Detect market and get appropriate company name
    market = detect_market(ticker) if ticker else 'KR'
    search_name = get_company_name(ticker) if ticker else None
    english_name = get_english_name(ticker) if ticker else None
    
    print(f"📰 [News] Getting news for: {search_name or query or 'market'} (Market: {market})")
    
    try:
        news_items = []
        english_titles_for_summary = []
        
        # Step 1: Try yfinance news (works well for US stocks)
        if ticker:
            stock = yf.Ticker(ticker)
            news = stock.news[:limit] if hasattr(stock, 'news') else []
            
            for item in news:
                content = item.get('content', item)
                title = content.get('title')
                
                # Collect English titles for summarization (US stocks)
                if market == 'US' and title:
                    english_titles_for_summary.append(title)
                
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
        
        # Step 2: Fallback to Google News search
        if not news_items and query:
            if query in TICKER_TO_NAME:
                query = TICKER_TO_NAME[query]
            
            try:
                from pygooglenews import GoogleNews
                
                # Use appropriate language based on market
                if market == 'US':
                    gn = GoogleNews(lang='en', country='US')
                    search_query = f"{english_name or query} stock"
                else:
                    gn = GoogleNews(lang='ko', country='KR')
                    search_query = query
                
                search = gn.search(search_query)
                
                for entry in search.get('entries', [])[:limit]:
                    title = entry.get('title')
                    if market == 'US' and title:
                        english_titles_for_summary.append(title)
                    
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
                
                # Fallback: Try with different query format
                if market == 'US':
                    try:
                        gn = GoogleNews(lang='en', country='US')
                        search = gn.search(f"{ticker} analysis outlook")
                        for entry in search.get('entries', [])[:limit]:
                            title = entry.get('title')
                            if title:
                                english_titles_for_summary.append(title)
                            news_items.append({
                                "title": title,
                                "publisher": entry.get('source', {}).get('title'),
                                "link": entry.get('link'),
                                "published": entry.get('published'),
                                "type": "news",
                                "thumbnail": None,
                                "language": "en"
                            })
                    except:
                        pass
        
        # Raise exception if no news found
        if not news_items:
            raise RuntimeError(f"No news found for '{search_name or query}'. Try a different search query.")
        
        # Step 3: Generate Korean summary for US stocks
        korean_summary = ""
        if market == 'US' and summarize_for_korean and english_titles_for_summary:
            korean_summary = _summarize_english_news_to_korean(
                english_titles_for_summary, 
                english_name or search_name
            )
        
        result = {
            "status": "success",
            "ticker": ticker,
            "company_name": search_name,
            "market": market,
            "query": query,
            "count": len(news_items),
            "news": news_items,
            "timestamp": datetime.now(pytz.timezone('Asia/Seoul')).isoformat()
        }
        
        # Add Korean summary only for US stocks
        if korean_summary:
            result["global_news_summary_kr"] = korean_summary
        
        return json.dumps(result, ensure_ascii=False)
        
    except RuntimeError:
        raise
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)})


