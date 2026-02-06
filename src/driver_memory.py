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


class DriverMemory:
    """
    Stores and retrieves historical volatility drivers for each stock.
    Enables targeted news searches based on what historically moves the stock.
    """
    
    def __init__(self, storage_file: str = "driver_memory.json"):
        self.storage_file = storage_file
        self.drivers: Dict[str, Dict[str, Any]] = {}
        self._load_memory()
        print("[DriverMemory] Initialized.")
    
    def _load_memory(self):
        """Load driver memory from JSON file."""
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, 'r', encoding='utf-8') as f:
                    self.drivers = json.load(f)
            except json.JSONDecodeError:
                self.drivers = {}
        else:
            self.drivers = {}
    
    def _save_memory(self):
        """Save driver memory to JSON file."""
        with open(self.storage_file, 'w', encoding='utf-8') as f:
            json.dump(self.drivers, f, ensure_ascii=False, indent=2)
    
    def get_drivers(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached drivers for a ticker.
        Returns None if not found or outdated (>30 days old).
        """
        if ticker not in self.drivers:
            return None
        
        driver_data = self.drivers[ticker]
        last_updated = driver_data.get("last_updated", "")
        
        # Check if data is stale (older than 30 days)
        if last_updated:
            try:
                update_date = datetime.strptime(last_updated, "%Y-%m-%d")
                if (datetime.now() - update_date).days > 30:
                    return None  # Stale data, needs refresh
            except ValueError:
                pass
        
        return driver_data
    
    def save_drivers(self, ticker: str, name: str, keywords: List[str], 
                     volatility_dates: List[str]):
        """Save driver keywords for a ticker."""
        self.drivers[ticker] = {
            "name": name,
            "drivers": keywords,
            "last_updated": datetime.now().strftime("%Y-%m-%d"),
            "volatility_dates": volatility_dates
        }
        self._save_memory()
        print(f"   💾 Saved drivers for {ticker}: {keywords}")
    
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
            extraction_prompt = f"""Analyze these news headlines for {name} ({ticker}) and extract the TOP 5 most important recurring themes or keywords that drive this stock's price.

News Headlines:
{news_context}

High Volatility Dates (days with big price moves):
{', '.join(volatility_dates)}

Focus on:
- Product names (HBM, GPU, iPhone)
- Market themes (AI, 반도체, 2차전지)
- Company events (파업, 실적, 인수합병)
- Competitive factors (경쟁사, 점유율)

Output ONLY a JSON array of 5 keywords, like:
["HBM", "AI", "파업", "TSMC", "반도체"]"""
            
            llm_response = self._call_llm(extraction_prompt)
            
            # Parse keywords from LLM response
            try:
                json_match = re.search(r'\[.*?\]', llm_response, re.DOTALL)
                if json_match:
                    keywords = json.loads(json_match.group(0))
                else:
                    keywords = ["주가", "실적", "뉴스"]
            except:
                keywords = ["주가", "실적", "뉴스"]
        else:
            # Default keywords if no news
            keywords = ["실적", "전망", "뉴스", "시장", "동향"]
        
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
