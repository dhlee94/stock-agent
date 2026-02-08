"""
Peer Group Analysis Tool - News-based Entity Mining + Cosine Similarity

This module implements the Context-Aware Financial Analyst workflow:
1. Entity Mining: Find co-mentioned companies from recent news
2. Data Acquisition: Get 30-day prices for target + peers
3. Vectorization: Convert prices to daily % change vectors
4. Cosine Similarity: Calculate similarity on returns (not prices)
5. Reference Proxy: Select peer with highest similarity (>0.7)
"""
import json
import re
import numpy as np
import yfinance as yf
from typing import List, Dict, Tuple, Optional
from datetime import datetime, timedelta

# Known company name to ticker mapping
COMPANY_TICKER_MAP = {
    # Korean Companies
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
    
    # US Companies
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

# Reverse mapping for display
TICKER_NAME_MAP = {v: k for k, v in COMPANY_TICKER_MAP.items()}


def _extract_entities_from_news(ticker: str, limit: int = 20) -> List[Tuple[str, int]]:
    """
    Extract co-mentioned company entities from recent news.
    Returns list of (company_name, mention_count) sorted by frequency.
    """
    print(f"   🔍 [Entity Mining] Searching news for {ticker}...")
    
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
            
            # Search for known company names in title
            for company_name, company_ticker in COMPANY_TICKER_MAP.items():
                # Skip if same as target
                if company_ticker == ticker:
                    continue
                    
                # Case-insensitive search
                if company_name.lower() in title.lower():
                    mention_counts[company_ticker] = mention_counts.get(company_ticker, 0) + 1
        
        # Sort by mention count
        sorted_mentions = sorted(mention_counts.items(), key=lambda x: x[1], reverse=True)
        
        print(f"   ✅ Found {len(sorted_mentions)} co-mentioned companies")
        return sorted_mentions[:5]  # Top 5
        
    except Exception as e:
        print(f"   ❌ Entity mining failed: {e}")
        return []


def _get_daily_returns(ticker: str, days: int = 30) -> Optional[np.ndarray]:
    """
    Get daily percentage returns for the past N days.
    Returns numpy array of daily returns (not prices).
    """
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period=f"{days + 5}d")  # Extra days for buffer
        
        if hist.empty or len(hist) < days:
            return None
        
        prices = hist['Close'].values[-days:]
        
        # Calculate daily percentage returns
        returns = np.diff(prices) / prices[:-1] * 100
        
        return returns
        
    except Exception:
        return None


def _cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """
    Calculate cosine similarity between two return vectors.
    Using returns instead of prices avoids scale bias.
    """
    if len(vec1) != len(vec2):
        # Align lengths
        min_len = min(len(vec1), len(vec2))
        vec1 = vec1[-min_len:]
        vec2 = vec2[-min_len:]
    
    dot_product = np.dot(vec1, vec2)
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    return dot_product / (norm1 * norm2)


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


def analyze_peer_group(ticker: str, similarity_threshold: float = 0.7) -> str:
    """
    Analyze peer group using news entity mining and cosine similarity on returns.
    
    Workflow:
    1. Entity Mining: Find top 5 co-mentioned companies from news
    2. Data Acquisition: Get 30-day closing prices
    3. Vectorization: Convert to daily % change vectors
    4. Cosine Similarity: Calculate similarity on returns
    5. Reference Proxy: Select peer with similarity > threshold
    
    Args:
        ticker: Target stock ticker
        similarity_threshold: Minimum similarity for reference proxy (default 0.7)
        
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
        # Step 1: Entity Mining
        co_mentioned = _extract_entities_from_news(ticker, limit=20)
        
        if not co_mentioned:
            result["entity_mining"] = {
                "found_peers": 0,
                "note": "No co-mentioned companies found in recent news"
            }
            result["synthesis"] = "뉴스에서 연관 기업을 찾지 못했습니다. 독립적으로 분석합니다."
            return json.dumps(result, ensure_ascii=False)
        
        result["entity_mining"] = {
            "found_peers": len(co_mentioned),
            "peers": [{"ticker": t, "name": TICKER_NAME_MAP.get(t, t), "mentions": c} 
                      for t, c in co_mentioned]
        }
        
        # Step 2 & 3: Get returns for target
        target_returns = _get_daily_returns(ticker)
        if target_returns is None:
            result["status"] = "partial"
            result["synthesis"] = "타겟 주식의 가격 데이터를 가져올 수 없습니다."
            return json.dumps(result, ensure_ascii=False)
        
        # Step 4: Calculate cosine similarity for each peer
        similarities = []
        
        for peer_ticker, mention_count in co_mentioned:
            peer_returns = _get_daily_returns(peer_ticker)
            
            if peer_returns is None:
                continue
            
            similarity = _cosine_similarity(target_returns, peer_returns)
            
            similarities.append({
                "ticker": peer_ticker,
                "name": TICKER_NAME_MAP.get(peer_ticker, peer_ticker),
                "mentions": mention_count,
                "cosine_similarity": round(similarity, 4),
                "momentum": _get_momentum_status(peer_ticker)
            })
        
        # Sort by similarity
        similarities.sort(key=lambda x: x["cosine_similarity"], reverse=True)
        result["similarity_analysis"] = similarities
        
        # Step 5: Select Reference Proxy
        high_similarity_peers = [s for s in similarities if s["cosine_similarity"] >= similarity_threshold]
        
        if high_similarity_peers:
            proxy = high_similarity_peers[0]
            result["reference_proxy"] = {
                "ticker": proxy["ticker"],
                "name": proxy["name"],
                "similarity": proxy["cosine_similarity"],
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
                f"📈 Reference Proxy: {proxy['name']} (유사도: {proxy['cosine_similarity']:.2f})\n"
                f"• 프록시 현재 모멘텀: {trend_text} (주간 {proxy_return:+.1f}%)\n"
                f"• {target_name}의 단기 전망: {outlook}\n"
                f"• 이유: 뉴스 동시 언급 빈도와 수익률 패턴이 유사하여 "
                f"{proxy['name']}의 움직임이 {target_name}에 영향을 줄 가능성이 높음."
            )
        else:
            # No high similarity peers
            max_sim = similarities[0] if similarities else None
            
            if max_sim:
                result["synthesis"] = (
                    f"⚠️ 뉴스 연관 기업 중 통계적으로 유의미한 가격 연동성(유사도 > {similarity_threshold})을 보이는 "
                    f"기업이 없습니다.\n"
                    f"• 최고 유사도: {max_sim['name']} ({max_sim['cosine_similarity']:.2f})\n"
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
