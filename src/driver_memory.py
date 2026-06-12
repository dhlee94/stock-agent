"""
DriverMemory - Historical Volatility Driver Analysis

This module identifies what moves each stock by analyzing:
1. High volatility dates in the past year
2. News on those dates
3. Recurring keywords that caused the movement
"""
import json
import os
import re
from datetime import datetime
from typing import List, Dict, Any, Optional

import yfinance as yf
from config import (
    KEYWORD_LLM_PROVIDER, KEYWORD_LLM_MODEL,
    GROQ_API_KEY, GEMINI_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY,
)
from database import get_top_drivers, get_ticker_info, add_driver, add_ticker

try:
    from .prompts import load_prompt
except ImportError:
    from prompts import load_prompt

# Strict Financial Stopwords - filter these out from driver keywords
FINANCIAL_STOPWORDS = {
    # Generic market terms (Korean)
    '뉴스', '속보', '특징주', '전망', '상승', '하락', '마감', '체결', '시장', '동향',
    '분석', '오늘', '내일', '어제', '급등', '급락', '매수', '매도', '추천', '투자',
    '주가', '주식', '증시', '코스피', '코스닥', '나스닥', '다우', 'S&P',
    # Generic market terms (English)
    'stock', 'market', 'news', 'update', 'report', 'analysis', 'today', 'yesterday',
    'price', 'buy', 'sell', 'hold', 'watch', 'breaking', 'alert', 'surge', 'drop',
}

# Ticker to Korean Company Name Mapping
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
    '034730.KS': 'SK',
    '030200.KS': 'KT',
    '017670.KS': 'SK텔레콤',
    '015760.KS': '한국전력',
    '032830.KS': '삼성생명',
    # US Stocks
    'AAPL': 'Apple',
    'MSFT': 'Microsoft',
    'GOOGL': 'Alphabet',
    'AMZN': 'Amazon',
    'NVDA': 'NVIDIA',
    'META': 'Meta',
    'TSLA': 'Tesla',
    'AMD': 'AMD',
    'INTC': 'Intel',
    'NFLX': 'Netflix',
}

def get_company_name(ticker: str) -> str:
    """Get company name from ticker, or return ticker if not found."""
    return TICKER_TO_NAME.get(ticker, ticker.split('.')[0])


class DriverMemory:
    """
    Stores and retrieves historical volatility drivers for each stock.
    Enables targeted news searches based on what historically moves the stock.
    """
    
    def __init__(self):
        print("[DriverMemory] Initialized with SQLite database.")


    _DRIVER_TTL_DAYS = 30

    def get_drivers(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached drivers for a ticker.
        Returns None if not found or older than 30 days.
        """
        from database import get_top_drivers, get_ticker_info, get_connection

        drivers = get_top_drivers(ticker)
        if not drivers:
            return None

        # TTL 체크: driver_memory 테이블의 최신 created_at 기준
        with get_connection() as conn:
            row = conn.execute(
                "SELECT MAX(created_at) as latest FROM driver_memory WHERE ticker = ?",
                (ticker,)
            ).fetchone()
        latest = row["latest"] if row and row["latest"] else None
        if latest:
            try:
                last_dt = datetime.strptime(latest[:10], "%Y-%m-%d")
                if (datetime.now() - last_dt).days > self._DRIVER_TTL_DAYS:
                    return None
            except ValueError:
                pass

        ticker_info = get_ticker_info(ticker)
        name = ticker_info['name'] if ticker_info else ticker
        keyword_drivers = [d['description'] for d in drivers if d['driver_type'] == 'keyword']

        return {
            "name": name,
            "drivers": keyword_drivers,
            "last_updated": latest[:10] if latest else datetime.now().strftime("%Y-%m-%d"),
            "volatility_dates": []
        }
    
    def save_drivers(self, ticker: str, name: str, keywords: List[str], 
                     volatility_dates: List[str]):
        """Save driver keywords for a ticker to database."""
        from database import add_driver, add_ticker, get_ticker_info
        
        # Ensure ticker exists
        info = get_ticker_info(ticker)
        if not info:
             market = 'KR' if '.KS' in ticker else 'US'
             add_ticker(ticker, name, None, market)
             
        # Add drivers
        for keyword in keywords:
            add_driver(
                ticker=ticker,
                name=name,
                driver_type='keyword',
                description=keyword,
                impact_direction='neutral',
                confidence=0.8
            )
        
        print(f"   💾 Saved drivers for {ticker} to database: {keywords}")
    
    def _call_llm(self, prompt: str) -> str:
        """Call LLM for keyword extraction. Provider selected via KEYWORD_LLM_PROVIDER."""
        if KEYWORD_LLM_PROVIDER == "groq" and GROQ_API_KEY:
            try:
                from groq import Groq
                client = Groq(api_key=GROQ_API_KEY)
                response = client.chat.completions.create(
                    model=KEYWORD_LLM_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=500
                )
                return response.choices[0].message.content
            except Exception as e:
                print(f"   ⚠️ Groq error: {e}. Falling back to Gemini...")

        if KEYWORD_LLM_PROVIDER == "openai" and OPENAI_API_KEY:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=OPENAI_API_KEY)
                response = client.chat.completions.create(
                    model=KEYWORD_LLM_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=500,
                )
                return response.choices[0].message.content
            except Exception as e:
                print(f"   ⚠️ OpenAI error: {e}. Falling back to Gemini...")

        if KEYWORD_LLM_PROVIDER == "anthropic" and ANTHROPIC_API_KEY:
            try:
                import anthropic
                client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
                response = client.messages.create(
                    model=KEYWORD_LLM_MODEL,
                    max_tokens=500,
                    temperature=0.3,
                    messages=[{"role": "user", "content": prompt}],
                )
                return response.content[0].text
            except Exception as e:
                print(f"   ⚠️ Anthropic error: {e}. Falling back to Gemini...")

        # Fallback (and default for KEYWORD_LLM_PROVIDER == "gemini"): Gemini.
        # Use the configured model only if the chosen provider is gemini;
        # otherwise fall back to a known-good default model.
        if GEMINI_API_KEY:
            try:
                import google.generativeai as genai
                genai.configure(api_key=GEMINI_API_KEY)
                gemini_model_name = KEYWORD_LLM_MODEL if KEYWORD_LLM_PROVIDER == "gemini" else "gemini-2.5-flash"
                model = genai.GenerativeModel(gemini_model_name)
                response = model.generate_content(prompt)
                return response.text
            except Exception as e:
                print(f"   ⚠️ Gemini error: {e}")
                return ""
        return ""
    
    def analyze_historical_drivers(self, ticker: str, name: str = "") -> Dict[str, Any]:
        """
        Phase A: Learning - Analyze historical volatility to find key drivers.
        
        1. Fetch 1-year price history
        2. Find top 5 days with >3% change
        3. Search news for those dates
        4. Extract recurring keywords via LLM
        5. Save to driver_memory.json
        """
        print(f"\n📊 [DriverMemory] Analyzing drivers for {ticker}...")
        
        # 1. Fetch 1-year price history
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1y")
            
            if hist.empty:
                return {"error": f"No price data for {ticker}"}
            
            # Get company name if not provided
            if not name:
                info = stock.info
                name = info.get("shortName", info.get("longName", ticker))
        except Exception as e:
            return {"error": f"Failed to fetch data: {str(e)}"}
        
        # 2. Calculate daily % change and find high volatility dates
        hist['pct_change'] = hist['Close'].pct_change() * 100
        hist['abs_change'] = hist['pct_change'].abs()
        
        # Filter days with >3% change
        high_vol = hist[hist['abs_change'] > 3.0].copy()
        
        if high_vol.empty:
            # Lower threshold if no extreme days
            high_vol = hist.nlargest(5, 'abs_change')
        else:
            high_vol = high_vol.nlargest(5, 'abs_change')
        
        volatility_dates = [d.strftime("%Y-%m-%d") for d in high_vol.index]
        print(f"   📅 High volatility dates: {volatility_dates}")
        
        # 3. Search news for those dates (Use robust news tool)
        news_texts = []
        try:
            # Try to import from tools, handling different path contexts
            try:
                from tools.stock.news import get_market_news
            except ImportError:
                try:
                    from src.tools.stock.news import get_market_news
                except ImportError:
                    # Fallback logic if import fails
                    get_market_news = None
            
            if get_market_news:
                # Fetch news using the robust tool (handles KR/US detection and Google News fallback)
                print(f"   📰 Searching news for drivers via get_market_news...")
                news_json = get_market_news(ticker=ticker, limit=15)
                news_data = json.loads(news_json)
                
                if "news" in news_data:
                    for item in news_data["news"]:
                        title = item.get('title', '')
                        if title:
                            news_texts.append(title)
            else:
                # Fallback to yfinance if tool import fails
                print(f"   ⚠️ News tool import failed, falling back to basic yfinance...")
                news_items = stock.news[:20] if hasattr(stock, 'news') else []
                for item in news_items:
                    title = item.get('title', '')
                    if title:
                        news_texts.append(title)
                        
        except Exception as e:
            print(f"   ⚠️ News search failed: {e}")
            news_texts = []
        
        # 4. Use LLM to extract recurring keywords
        if news_texts:
            news_context = "\n".join(news_texts[:15])
            extraction_prompt = load_prompt(
                "driver_memory/keyword_extraction",
                name=name,
                ticker=ticker,
                news_context=news_context,
                volatility_dates=", ".join(volatility_dates),
            )

            llm_response = self._call_llm(extraction_prompt)
            
            # Parse keywords from LLM response
            try:
                json_match = re.search(r'\[.*?\]', llm_response, re.DOTALL)
                if json_match:
                    raw_keywords = json.loads(json_match.group(0))
                    # Filter out stopwords
                    keywords = [
                        kw for kw in raw_keywords 
                        if kw.lower() not in FINANCIAL_STOPWORDS and len(kw) > 1
                    ]
                    # If all filtered out, use defaults
                    if len(keywords) < 2:
                        keywords = ["실적발표", "기술", "경쟁사"]
                else:
                    keywords = ["실적발표", "기술", "경쟁사"]
            except Exception as e:
                print(f"   ⚠️ [DriverMemory] Keyword parse failed: {e}")
                keywords = ["실적발표", "기술", "경쟁사"]
        else:
            # Default keywords if no news - still use specific terms
            keywords = ["실적발표", "신사업", "경쟁사", "기술개발", "공급계약"]
        
        print(f"   🔑 Extracted drivers: {keywords}")
        
        # 5. Save to memory
        self.save_drivers(ticker, name, keywords, volatility_dates)
        
        return {
            "ticker": ticker,
            "name": name,
            "drivers": keywords,
            "volatility_dates": volatility_dates,
            "status": "success"
        }


def analyze_drivers(ticker: str, name: str = "") -> str:
    """
    MCP Tool wrapper for driver analysis.
    Returns formatted string for agent consumption.
    """
    dm = DriverMemory()
    
    # Check cache first
    cached = dm.get_drivers(ticker)
    if cached:
        return json.dumps({
            "source": "cache",
            "ticker": ticker,
            "name": cached.get("name", ""),
            "drivers": cached.get("drivers", []),
            "last_updated": cached.get("last_updated", ""),
            "message": f"Using cached drivers: {', '.join(cached.get('drivers', []))}"
        }, ensure_ascii=False)
    
    # Analyze if not cached
    result = dm.analyze_historical_drivers(ticker, name)
    return json.dumps(result, ensure_ascii=False)


if __name__ == "__main__":
    # Test
    dm = DriverMemory()
    result = dm.analyze_historical_drivers("005930.KS", "삼성전자")
    print("\n📋 Result:")
    print(json.dumps(result, ensure_ascii=False, indent=2))
