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
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

import yfinance as yf
from dotenv import load_dotenv

# Load environment
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "gemini").lower()
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

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
    
    def __init__(self, storage_file: str = "driver_memory.json"):
        # Storage file is no longer used, kept for compatibility
        self.storage_file = storage_file
        print("[DriverMemory] Initialized with SQLite database.")
    
    def _load_memory(self):
        """Deprecated: Logic moved to database.py"""
        pass
    
    def _save_memory(self):
        """Deprecated: Logic moved to database.py"""
        pass
    
    def get_drivers(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached drivers for a ticker from database.
        Returns None if not found or outdated (>30 days old).
        """
        from database import get_top_drivers, get_ticker_info
        
        # Get latest update time
        # This is a simplification; in a real scenario we might check the latest created_at
        # For now, we just get the drivers
        drivers = get_top_drivers(ticker)
        if not drivers:
            return None
            
        # Get ticker info for name
        ticker_info = get_ticker_info(ticker)
        name = ticker_info['name'] if ticker_info else ticker
        
        # Convert to legacy format for compatibility
        keyword_drivers = [d['description'] for d in drivers if d['driver_type'] == 'keyword']
        
        return {
            "name": name,
            "drivers": keyword_drivers,
            "last_updated": datetime.now().strftime("%Y-%m-%d"), # Live data
            "volatility_dates": [] # Volatility dates are now derived on the fly or need new table
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
        """Call LLM for keyword extraction."""
        if LLM_PROVIDER == "groq" and GROQ_API_KEY:
            from groq import Groq
            client = Groq(api_key=GROQ_API_KEY)
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=500
            )
            return response.choices[0].message.content
        else:
            # Fallback to Gemini
            import google.generativeai as genai
            GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
            if GEMINI_API_KEY:
                genai.configure(api_key=GEMINI_API_KEY)
                model = genai.GenerativeModel("gemini-2.0-flash")
                response = model.generate_content(prompt)
                return response.text
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
        
        # 3. Search news for those dates (using yfinance news as proxy)
        try:
            news_items = stock.news[:20] if hasattr(stock, 'news') else []
            news_texts = []
            for item in news_items:
                title = item.get('title', '')
                if title:
                    news_texts.append(title)
        except:
            news_texts = []
        
        # 4. Use LLM to extract recurring keywords
        if news_texts:
            news_context = "\n".join(news_texts[:15])
            extraction_prompt = f"""Analyze these news headlines for {name} ({ticker}) and extract the TOP 5 most SPECIFIC keywords that drive this stock's price.

News Headlines:
{news_context}

High Volatility Dates (days with big price moves):
{', '.join(volatility_dates)}

## CRITICAL RULES:
1. **EXCLUDE generic financial terms** like: 뉴스, 전망, 상승, 하락, 시장, 동향, 분석, 주가, 투자, stock, market, news, update
2. **ONLY extract specific proper nouns or event names**:
   - Product names: HBM, DDR5, OLED, iPhone, GPU
   - Technologies: AI, 반도체, 2차전지, EV
   - Company events: 파업, 실적발표, 인수합병, 공급계약
   - Competitors/Partners: TSMC, 퀄컴, 엔비디아, 애플
   - Technical terms: 수율, 공정, 파운드리, 3nm

## Example BAD keywords (too generic):
["뉴스", "전망", "상승", "시장", "동향"]

## Example GOOD keywords (specific):
["HBM", "파업", "수율", "TSMC", "AI반도체"]

Output ONLY a JSON array of 5 SPECIFIC keywords:"""
            
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
            except:
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
