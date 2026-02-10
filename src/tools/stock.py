"""
Stock Tool - Chronos + FinBERT를 활용한 AI 기반 주식 분석 도구
"""
import json
from ..stock_tool import analyze_stock as _analyze_stock


def analyze_stock(ticker: str, name: str, market: str = "KR") -> str:
    """
    Chronos + FinBERT 멀티모달 결합 모델을 사용해 주식을 분석합니다.
    현재가, AI 점수, 매수/매도/보유 추천 등을 JSON 문자열로 반환합니다.
    
    Args:
        ticker: 주식 티커(symbol) (예: "005930.KS", "NVDA")
        name: 회사명 (예: "삼성전자", "NVIDIA")
        market: "KR" = 한국, "US" = 미국
    """
    print(f"📈 [Stock] 종목 분석 시작: {name} ({ticker}), 시장={market}")
    try:
        result = _analyze_stock(ticker, name, market)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False)
