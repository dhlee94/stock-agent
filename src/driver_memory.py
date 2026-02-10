"""
DriverMemory - 과거 변동성(Volatility) 드라이버 분석 모듈

이 모듈은 다음 과정을 통해 **각 종목의 주가를 움직이는 핵심 요인**을 찾아냅니다.
1. 최근 1년치 가격 데이터에서 변동성이 컸던 날짜를 찾습니다.
2. 해당 날짜 전후의 뉴스를 수집합니다.
3. 반복적으로 등장하는 핵심 키워드를 LLM으로 추출하여 드라이버로 저장합니다.
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
    """티커(symbol)로부터 회사 이름을 조회합니다. 없으면 티커에서 코드만 잘라 반환합니다."""
    return TICKER_TO_NAME.get(ticker, ticker.split('.')[0])


class DriverMemory:
    """
    각 종목별로 과거 변동성을 유발했던 드라이버(키워드)를 저장·조회하는 클래스입니다.
    이 정보를 활용해 **더 타깃팅된 뉴스 검색/분석**을 수행할 수 있습니다.
    """
    
    def __init__(self, storage_file: str = "driver_memory.json"):
        # Storage file is no longer used, kept for compatibility
        self.storage_file = storage_file
        print("[DriverMemory] SQLite 데이터베이스 기반으로 초기화되었습니다.")
    
    def _load_memory(self):
        """더 이상 사용되지 않습니다. 관련 로직은 database.py로 이전되었습니다."""
        pass
    
    def _save_memory(self):
        """더 이상 사용되지 않습니다. 관련 로직은 database.py로 이전되었습니다."""
        pass
    
    def get_drivers(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        주어진 티커에 대한 드라이버 정보를 DB에서 조회합니다.
        (단순 조회이며, 최신성 판단은 현재는 생략되어 있습니다.)
        """
        from database import get_top_drivers, get_ticker_info
        
        # Get latest update time
        # 실제 구현에서는 created_at 기준으로 최신성을 판단할 수 있으나,
        # 현재 버전에서는 단순 조회만 수행합니다.
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
        """특정 티커에 대한 드라이버 키워드를 DB에 저장합니다."""
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
        
        print(f"   💾 {ticker}에 대한 드라이버 키워드를 DB에 저장했습니다: {keywords}")
    
    def _call_llm(self, prompt: str) -> str:
        """드라이버 키워드 추출을 위해 LLM을 호출합니다."""
        if LLM_PROVIDER == "groq" and GROQ_API_KEY:
            try:
                from groq import Groq
                client = Groq(api_key=GROQ_API_KEY)
                response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=500
                )
                return response.choices[0].message.content
            except Exception as e:
                print(f"   ⚠️ Groq 호출 중 오류 발생: {e}. Gemini로 폴백합니다...")
                # Fallback continues below
        
        # Fallback to Gemini
        import google.generativeai as genai
        GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if GEMINI_API_KEY:
            try:
                genai.configure(api_key=GEMINI_API_KEY)
                model = genai.GenerativeModel("gemini-2.0-flash")
                response = model.generate_content(prompt)
                return response.text
            except Exception as e:
                print(f"   ⚠️ Gemini 호출 중 오류 발생: {e}")
                return ""
        return ""
    
    def analyze_historical_drivers(self, ticker: str, name: str = "") -> Dict[str, Any]:
        """
        Phase A: 학습 단계 - 과거 변동성 구간을 분석해 핵심 드라이버를 찾습니다.
        
        1. 최근 1년 가격 데이터를 가져옵니다.
        2. 일일 등락률이 3% 이상이었던 상·하락 구간을 찾습니다.
        3. 해당 구간 전후의 뉴스를 수집합니다.
        4. LLM을 사용해 반복적으로 등장하는 키워드를 추출합니다.
        5. 결과를 DB에 저장합니다.
        """
        print(f"\n📊 [DriverMemory] {ticker}의 변동성 드라이버를 분석합니다...")
        
        # 1. Fetch 1-year price history
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1y")
            
            if hist.empty:
                return {"error": f"{ticker}에 대한 가격 데이터가 없습니다."}
            
            # Get company name if not provided
            if not name:
                info = stock.info
                name = info.get("shortName", info.get("longName", ticker))
        except Exception as e:
            return {"error": f"가격 데이터를 가져오지 못했습니다: {str(e)}"}
        
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
        print(f"   📅 변동성이 컸던 날짜들: {volatility_dates}")
        
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
                print("   📰 get_market_news를 통해 변동성 원인 뉴스를 조회합니다...")
                news_json = get_market_news(ticker=ticker, limit=15)
                news_data = json.loads(news_json)
                
                if "news" in news_data:
                    for item in news_data["news"]:
                        title = item.get('title', '')
                        if title:
                            news_texts.append(title)
            else:
                # Fallback to yfinance if tool import fails
                print("   ⚠️ 뉴스 도구를 불러오지 못해 yfinance 기본 뉴스로 폴백합니다...")
                news_items = stock.news[:20] if hasattr(stock, 'news') else []
                for item in news_items:
                    title = item.get('title', '')
                    if title:
                        news_texts.append(title)
                        
        except Exception as e:
            print(f"   ⚠️ 뉴스 조회 중 오류가 발생했습니다: {e}")
            news_texts = []
        
        # 4. Use LLM to extract recurring keywords
        if news_texts:
            news_context = "\n".join(news_texts[:15])
            extraction_prompt = f"""다음은 {name} ({ticker}) 관련 뉴스 헤드라인 목록입니다.
이 헤드라인들을 분석하여 **이 종목의 주가를 움직이는 구체적인 요인**을 나타내는
가장 중요한 키워드 5개를 뽑아 주세요.

[뉴스 헤드라인]
{news_context}

[변동성 구간 날짜] (일일 등락률이 큰 날)
{', '.join(volatility_dates)}

## 중요 규칙
1. 아래와 같은 일반적인 금융 용어는 모두 제외해야 합니다.
   - 예: 뉴스, 전망, 상승, 하락, 시장, 동향, 분석, 주가, 투자, stock, market, news, update 등
2. **구체적인 고유명사나 이벤트 이름만** 추출하세요.
   - 제품명: HBM, DDR5, OLED, iPhone, GPU
   - 기술명: AI, 반도체, 2차전지, EV
   - 회사 이벤트: 파업, 실적발표, 인수합병, 공급계약
   - 경쟁사/파트너: TSMC, 퀄컴, 엔비디아, 애플
   - 기술 용어: 수율, 공정, 파운드리, 3nm

## 나쁜 예 (너무 일반적)
["뉴스", "전망", "상승", "시장", "동향"]

## 좋은 예 (구체적)
["HBM", "파업", "수율", "TSMC", "AI반도체"]

반드시 **JSON 배열 형식**으로만 응답하세요 (예: ["HBM", "파업", "수율", "TSMC", "AI반도체"])."""
            
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
            except Exception:
                keywords = ["실적발표", "기술", "경쟁사"]
        else:
            # Default keywords if no news - still use specific terms
            keywords = ["실적발표", "신사업", "경쟁사", "기술개발", "공급계약"]
        
        print(f"   🔑 추출된 드라이버 키워드: {keywords}")
        
        # 5. Save to memory
        self.save_drivers(ticker, name, keywords, volatility_dates)
        
        return {
            "ticker": ticker,
            "name": name,
            "drivers": keywords,
            "volatility_dates": volatility_dates,
            "status": "success",
        }


def analyze_drivers(ticker: str, name: str = "") -> str:
    """
    MCP 도구용 래퍼 함수로, 드라이버 분석을 수행하고 JSON 문자열을 반환합니다.
    에이전트가 바로 사용할 수 있는 형식으로 가공됩니다.
    """
    dm = DriverMemory()
    
    # Check cache first
    cached = dm.get_drivers(ticker)
    if cached:
        return json.dumps(
            {
                "source": "cache",
                "ticker": ticker,
                "name": cached.get("name", ""),
                "drivers": cached.get("drivers", []),
                "last_updated": cached.get("last_updated", ""),
                "message": f"캐시된 드라이버를 사용합니다: {', '.join(cached.get('drivers', []))}",
            },
            ensure_ascii=False,
        )
    
    # Analyze if not cached
    result = dm.analyze_historical_drivers(ticker, name)
    return json.dumps(result, ensure_ascii=False)


if __name__ == "__main__":
    # 간단 테스트
    dm = DriverMemory()
    result = dm.analyze_historical_drivers("005930.KS", "삼성전자")
    print("\n📋 분석 결과:")
    print(json.dumps(result, ensure_ascii=False, indent=2))
