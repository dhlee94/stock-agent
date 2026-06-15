import yfinance as yf
import pandas as pd
import numpy as np
from typing import List, Dict, Any


class StockDataLoader:
    """
    주가 및 뉴스 데이터를 수집하는 통합 로더.
    (시계열 예측 모델 제거 후 뉴스 감성 분석용 데이터 수집 위주로 동작)
    """

    def __init__(self, symbol: str, name: str, market_type: str = "KR"):
        self.symbol = symbol
        self.name = name
        self.market_type = market_type
        self.ticker = yf.Ticker(symbol)

    def get_news(self, limit: int = 10) -> List[str]:
        """최신 뉴스 헤드라인 수집."""
        news = self.ticker.news
        if not news:
            return []
        # 제목만 추출하여 리스트로 반환
        return [item.get("title", "") for item in news[:limit] if item.get("title")]

    def get_price_history(self, period: str = "1mo") -> pd.DataFrame:
        """주가 히스토리 수집."""
        df = self.ticker.history(period=period)
        return df

    def prepare_all(self) -> Dict[str, Any]:
        """분석에 필요한 모든 데이터 준비."""
        df = self.get_price_history()
        news = self.get_news()

        if df.empty:
            return {
                "price_context": None,
                "current_price": 0,
                "news": news,
                "volatility": 0,
            }

        # 변동성 계산 (최근 20일 기준 표준편차)
        volatility = df["Close"].pct_change().std()

        return {
            "current_price": df["Close"].iloc[-1],
            "news": news,
            "volatility": 0 if np.isnan(volatility) else volatility,
        }
