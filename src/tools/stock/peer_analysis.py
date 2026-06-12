"""
Peer Group Analysis Tool - STL Trend Decomposition + LLM Fallback

This module implements the Context-Aware Financial Analyst workflow:
1. Entity Mining: Find co-mentioned companies from recent news
2. LLM Fallback: If no peers found, use LLM to identify industry competitors
3. STL Decomposition: Extract trend component (Seasonal-Trend-Loess)
4. Pearson Correlation: Calculate trend similarity
5. Reference Proxy: Select peer with correlation > 0.7 for Reflector verification
"""
import json
import re
import numpy as np
import yfinance as yf
from typing import List, Dict, Tuple, Optional
from datetime import datetime
import sys
import os

# Add src to path for database import
SRC_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), '../..'))
if SRC_DIR not in sys.path:
    sys.path.append(SRC_DIR)

try:
    from database import get_sector_competitors as db_get_competitors
except ImportError:
    # Fallback/Mock for testing without DB
    def db_get_competitors(ticker: str) -> List[str]: return []

def get_sector_competitors(ticker: str) -> List[str]:
    """Get competitors for a ticker from database."""
    return db_get_competitors(ticker)

# Known company name to ticker mapping - KOREAN MARKET
KR_COMPANY_TICKER_MAP = {
    "삼성전자": "005930.KS",
    "삼성": "005930.KS",
    "SK하이닉스": "000660.KS",
    "하이닉스": "000660.KS",
    "LG전자": "066570.KS",
    "현대차": "005380.KS",
    "현대자동차": "005380.KS",
    "기아": "000270.KS",
    "네이버": "035420.KS",
    "NAVER": "035420.KS",
    "카카오": "035720.KS",
    "LG에너지솔루션": "373220.KS",
    "삼성SDI": "006400.KS",
    "포스코홀딩스": "005490.KS",
    "셀트리온": "068270.KS",
    "한화에어로스페이스": "012450.KS",
    "현대모비스": "012330.KS",
    "KB금융": "105560.KS",
    "신한지주": "055550.KS",
}

# Known company name to ticker mapping - US MARKET
US_COMPANY_TICKER_MAP = {
    "NVIDIA": "NVDA",
    "엔비디아": "NVDA",
    "Apple": "AAPL",
    "애플": "AAPL",
    "Microsoft": "MSFT",
    "마이크로소프트": "MSFT",
    "Google": "GOOGL",
    "Alphabet": "GOOGL",
    "구글": "GOOGL",
    "Amazon": "AMZN",
    "아마존": "AMZN",
    "Tesla": "TSLA",
    "테슬라": "TSLA",
    "Meta": "META",
    "메타": "META",
    "AMD": "AMD",
    "Intel": "INTC",
    "인텔": "INTC",
    "Qualcomm": "QCOM",
    "퀄컴": "QCOM",
    "TSMC": "TSM",
    "Broadcom": "AVGO",
    "Micron": "MU",
    "마이크론": "MU",
}


def _detect_market(ticker: str) -> str:
    """Detect market from ticker suffix."""
    if ".KS" in ticker or ".KQ" in ticker:
        return "KR"
    return "US"


def _get_company_map_for_market(market: str) -> dict:
    """Get the appropriate company map for the target market.
    market_utils.NAME_TO_TICKER를 기반으로 병합하고,
    로컬 항목(별칭 포함)을 우선 적용한다.
    """
    local = KR_COMPANY_TICKER_MAP if market == "KR" else US_COMPANY_TICKER_MAP
    try:
        from market_utils import NAME_TO_TICKER as _mu
        return {**_mu, **local}
    except ImportError:
        return local


# Combined mapping for display names
TICKER_NAME_MAP = {**{v: k for k, v in KR_COMPANY_TICKER_MAP.items()}, 
                   **{v: k for k, v in US_COMPANY_TICKER_MAP.items()}}


def _extract_entities_from_news(ticker: str, limit: int = 20) -> List[Tuple[str, int]]:
    """
    Extract co-mentioned company entities from recent news.
    Only returns peers from the SAME MARKET (KR or US).
    Returns list of (company_name, mention_count) sorted by frequency.
    """
    # Detect market of target ticker
    market = _detect_market(ticker)
    company_map = _get_company_map_for_market(market)
    
    print(f"   🔍 [Entity Mining] Searching news for {ticker} (Market: {market})...")
    
    try:
        stock = yf.Ticker(ticker)
        news = stock.news[:limit] if hasattr(stock, 'news') else []
        
        if not news:
            print(f"   ⚠️ No news found for {ticker}")
            return []
        
        # Count company mentions across all news titles
        mention_counts = {}
        
        for item in news:
            content = item.get('content', item)
            title = content.get('title', '')
            
            # Search for known company names in title (SAME MARKET ONLY)
            for company_name, company_ticker in company_map.items():
                # Skip if same as target
                if company_ticker == ticker:
                    continue
                    
                # Case-insensitive search
                if company_name.lower() in title.lower():
                    mention_counts[company_ticker] = mention_counts.get(company_ticker, 0) + 1
        
        # Sort by mention count
        sorted_mentions = sorted(mention_counts.items(), key=lambda x: x[1], reverse=True)
        
        print(f"   ✅ Found {len(sorted_mentions)} co-mentioned {market} companies")
        return sorted_mentions[:5]  # Top 5
        
    except Exception as e:
        print(f"   ❌ Entity mining failed: {e}")
        return []


def _get_price_series(ticker: str, days: int = 60) -> Optional[np.ndarray]:
    """
    Get daily closing prices for STL decomposition.
    Requires more days for proper seasonal decomposition.
    """
    try:
        stock = yf.Ticker(ticker)
        # 60 trading days ≈ 84 calendar days; add buffer for holidays
        calendar_days = int(days * 1.5) + 10
        hist = stock.history(period=f"{calendar_days}d")
        
        if hist.empty or len(hist) < days:
            return None
        
        prices = hist['Close'].values[-days:]
        return prices
        
    except Exception:
        return None


def _extract_stl_trend(prices: np.ndarray, period: int = 5) -> Optional[np.ndarray]:
    """
    Extract Trend component using STL decomposition.
    
    STL = Seasonal-Trend decomposition using LOESS
    - Seasonal: Repeating patterns (weekly cycles, etc.)
    - Trend: Underlying long-term movement (THIS IS WHAT WE COMPARE)
    - Residual: Random noise
    
    Args:
        prices: Daily closing prices
        period: Seasonal period (5 for weekly trading days)
    
    Returns:
        Trend component as numpy array
    """
    try:
        from statsmodels.tsa.seasonal import STL
        import pandas as pd
        
        # STL requires at least 2 full periods
        if len(prices) < period * 2:
            return None
        
        # Create pandas Series for STL
        series = pd.Series(prices)
        
        # Apply STL decomposition
        stl = STL(series, period=period, robust=True)
        result = stl.fit()
        
        # Return the Trend component
        return result.trend.values
        
    except Exception as e:
        print(f"      ⚠️ STL decomposition failed: {e}")
        return None


def _trend_similarity(trend1: np.ndarray, trend2: np.ndarray) -> float:
    """
    Calculate similarity between two STL Trend components.
    Uses Pearson correlation instead of cosine similarity for trends.
    
    Pearson correlation is better for trends because:
    1. It measures linear relationship regardless of scale
    2. Values range from -1 (inverse) to +1 (perfectly correlated)
    3. 0 means no correlation
    """
    if len(trend1) != len(trend2):
        # Align lengths
        min_len = min(len(trend1), len(trend2))
        trend1 = trend1[-min_len:]
        trend2 = trend2[-min_len:]
    
    # Remove any NaN values from STL output
    mask = ~(np.isnan(trend1) | np.isnan(trend2))
    trend1 = trend1[mask]
    trend2 = trend2[mask]
    
    if len(trend1) < 10:
        return 0.0
    
    # Pearson correlation
    mean1 = np.mean(trend1)
    mean2 = np.mean(trend2)
    
    cov = np.sum((trend1 - mean1) * (trend2 - mean2))
    std1 = np.sqrt(np.sum((trend1 - mean1) ** 2))
    std2 = np.sqrt(np.sum((trend2 - mean2) ** 2))
    
    if std1 == 0 or std2 == 0:
        return 0.0
    
    return cov / (std1 * std2)


def _get_momentum_status(ticker: str) -> Dict:
    """Get current momentum and trend status for a stock."""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1mo")
        
        if hist.empty:
            return {"status": "unknown"}
        
        prices = hist['Close'].values
        current = float(prices[-1])
        ma5 = float(np.mean(prices[-5:])) if len(prices) >= 5 else current
        ma20 = float(np.mean(prices[-20:])) if len(prices) >= 20 else current
        
        # Calculate momentum
        weekly_return = float(((prices[-1] / prices[-5]) - 1) * 100) if len(prices) >= 5 else 0.0
        
        # Trend direction
        trend = "bullish" if current > ma20 else "bearish"
        
        return {
            "current_price": round(current, 2),
            "ma5": round(ma5, 2),
            "ma20": round(ma20, 2),
            "weekly_return_pct": round(weekly_return, 2),
            "trend": trend,
            "above_ma5": bool(current > ma5),
            "above_ma20": bool(current > ma20),
        }
        
    except Exception:
        return {"status": "error"}


def analyze_peer_group(
    ticker: str, 
    similarity_threshold: float = 0.7,
    compare_with: Optional[List[str]] = None,
    stl_days: int = 60
) -> str:
    """
    Analyze peer group using news entity mining or user-specified targets.
    
    Workflow:
    1. Entity Mining: Find top 5 co-mentioned companies from news (or use compare_with)
    2. LLM/Sector Fallback: If no peers found, use SECTOR_COMPETITORS mapping
    3. STL Decomposition: Extract trend component (configurable period)
    4. Pearson Correlation: Calculate trend similarity
    5. Reference Proxy: Select peer with correlation > threshold
    
    Args:
        ticker: Target stock ticker
        similarity_threshold: Minimum correlation for reference proxy (default 0.7)
        compare_with: List of tickers to compare with (bypasses news mining if provided)
        stl_days: Number of days for STL analysis (default 60, min 14 for seasonal decomposition)
        
    Returns:
        JSON with peer analysis results
    """
    print(f"\n📊 [Peer Analysis] Analyzing peer group for {ticker}...")
    
    result = {
        "status": "success",
        "ticker": ticker,
        "timestamp": datetime.now().isoformat(),
        "entity_mining": {},
        "similarity_analysis": [],
        "reference_proxy": None,
        "synthesis": "",
    }
    
    try:
        # Step 1: Entity Mining (or use user-specified targets)
        if compare_with and len(compare_with) > 0:
            # User specified comparison targets - skip news mining
            print(f"   📌 [User Specified] Comparing with: {compare_with}")
            co_mentioned = [(t, 0) for t in compare_with]  # 0 mentions since user-specified
            result["entity_mining"] = {
                "found_peers": len(compare_with),
                "mode": "user_specified",
                "peers": [{"ticker": t, "name": TICKER_NAME_MAP.get(t, t), "mentions": 0} 
                          for t in compare_with]
            }
        else:
            # Auto-search from news
            co_mentioned = _extract_entities_from_news(ticker, limit=20)
            
            if not co_mentioned:
                result["entity_mining"] = {
                    "found_peers": 0,
                    "mode": "news_mining",
                    "note": "No co-mentioned companies found in recent news"
                }
                result["synthesis"] = "뉴스에서 연관 기업을 찾지 못했습니다. 독립적으로 분석합니다."
                return json.dumps(result, ensure_ascii=False)
            
            result["entity_mining"] = {
                "found_peers": len(co_mentioned),
                "mode": "news_mining",
                "peers": [{"ticker": t, "name": TICKER_NAME_MAP.get(t, t), "mentions": c} 
                          for t, c in co_mentioned]
            }
        
        # Step 2: Get price series and extract STL Trend for target
        target_prices = _get_price_series(ticker, days=stl_days)
        if target_prices is None:
            result["status"] = "partial"
            result["synthesis"] = "타겟 주식의 가격 데이터를 가져올 수 없습니다."
            return json.dumps(result, ensure_ascii=False)
        
        target_trend = _extract_stl_trend(target_prices)
        if target_trend is None:
            result["status"] = "partial"
            result["synthesis"] = "타겟 주식의 STL 분해에 실패했습니다."
            return json.dumps(result, ensure_ascii=False)
        
        print(f"   📈 [STL] Extracted trend component for {ticker}")
        
        # Step 3: Calculate STL Trend similarity for each peer
        similarities = []
        
        for peer_ticker, mention_count in co_mentioned:
            peer_prices = _get_price_series(peer_ticker, days=stl_days)
            
            if peer_prices is None:
                continue
            
            peer_trend = _extract_stl_trend(peer_prices)
            if peer_trend is None:
                continue
            
            # Use Pearson correlation on Trend components
            similarity = _trend_similarity(target_trend, peer_trend)
            
            similarities.append({
                "ticker": peer_ticker,
                "name": TICKER_NAME_MAP.get(peer_ticker, peer_ticker),
                "mentions": mention_count,
                "trend_correlation": round(float(similarity), 4),  # Renamed from cosine_similarity
                "momentum": _get_momentum_status(peer_ticker)
            })
        
        # Sort by similarity
        similarities.sort(key=lambda x: x["trend_correlation"], reverse=True)
        result["similarity_analysis"] = similarities
        
        # Step 5: Select Reference Proxy
        high_similarity_peers = [s for s in similarities if s["trend_correlation"] >= similarity_threshold]
        
        if high_similarity_peers:
            proxy = high_similarity_peers[0]
            result["reference_proxy"] = {
                "ticker": proxy["ticker"],
                "name": proxy["name"],
                "trend_correlation": proxy["trend_correlation"],
                "momentum": proxy["momentum"]
            }
            
            # Generate synthesis
            target_name = TICKER_NAME_MAP.get(ticker, ticker)
            proxy_trend = proxy["momentum"].get("trend", "unknown")
            proxy_return = proxy["momentum"].get("weekly_return_pct", 0)
            
            if proxy_trend == "bullish":
                trend_text = "상승 추세"
                outlook = "긍정적"
            else:
                trend_text = "하락 추세"
                outlook = "부정적"
            
            result["synthesis"] = (
                f"📈 Reference Proxy: {proxy['name']} (Trend 상관계수: {proxy['trend_correlation']:.2f})\n"
                f"• STL 분해로 추출한 Trend 성분 비교 결과\n"
                f"• 프록시 현재 모멘텀: {trend_text} (주간 {proxy_return:+.1f}%)\n"
                f"• {target_name}의 단기 전망: {outlook}\n"
                f"• 이유: {proxy['name']}와 Trend가 유사하여 동반 움직임 예상."
            )
        else:
            # No high similarity peers
            max_sim = similarities[0] if similarities else None
            
            if max_sim:
                result["synthesis"] = (
                    f"⚠️ 뉴스 연관 기업 중 유의미한 Trend 상관관계(> {similarity_threshold})를 보이는 "
                    f"기업이 없습니다.\n"
                    f"• 최고 상관계수: {max_sim['name']} ({max_sim['trend_correlation']:.2f})\n"
                    f"• 결론: 이 종목은 섹터 전반 추세보다 개별 요인에 더 민감할 수 있습니다."
                )
            else:
                result["synthesis"] = "연관 기업의 가격 데이터를 가져올 수 없습니다."
        
        print(f"   ✅ Peer analysis complete")
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        return json.dumps(result, ensure_ascii=False)


if __name__ == "__main__":
    # Test
    import sys
    ticker = sys.argv[1] if len(sys.argv) > 1 else "005930.KS"
    result = analyze_peer_group(ticker)
    print(result)
