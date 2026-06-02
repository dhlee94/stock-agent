import yfinance as yf
import pandas as pd
import numpy as np
from datetime import timezone
import sys
import os
# Add src to path if needed for local utility import
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
from utils.google_news import GoogleNews
from statsmodels.tsa.seasonal import seasonal_decompose

class StockDataLoader:
    def __init__(self, ticker_symbol, ticker_name, market_type):
        self.symbol = ticker_symbol
        self.market_type = market_type
        self.name = ticker_name
        if market_type == "KR":
          self.gn = GoogleNews(lang='ko', country='KR')
        elif market_type == "US":
          self.gn = GoogleNews(lang='en', country='US')
        else:
            raise ValueError(f"Invalid market_type: '{market_type}'. Supported types are 'KR' or 'US'.")
        
    def fetch_price_data(self, period='5d', interval='5m'):
        """주가 데이터 수집"""
        df = yf.Ticker(self.symbol).history(period=period, interval=interval)
        if df.empty:
            raise ValueError(f"No data found for {self.symbol}")
        return df

    def get_news(self, limit=5):
        """뉴스 헤드라인 수집"""
        if self.market_type == "KR":
          search = self.gn.search(f'{self.name} 주가')
        else:
          search = self.gn.search(f'{self.name} stock')
        titles = [entry.title for entry in search['entries'][:limit]]
        return titles if titles else ["특이 사항 없음"]

    def get_stl_features(self, df, period=12):
        """
        STL (Seasonal-Trend Decomposition) 수행
        intveral이 10분이므로, period=12는 약 2시간(120분) 주기를 의미한다고 가정
        데이터 양이 적으면 period를 줄여야 함
        """
        if len(df) < period * 2:
            return None # 데이터 부족 시 스킵

        # 'Close' 가격 기준 분해
        decomposition = seasonal_decompose(df['Close'], model='additive', period=period, extrapolate_trend='freq')
        
        return {
            'trend': decomposition.trend.iloc[-1],      # 현재 추세값
            'seasonal': decomposition.seasonal.iloc[-1], # 현재 계절성 값
            'resid': decomposition.resid.iloc[-1]        # 잔차
        }

    def fetch_daily(self, period='3mo'):
        """일봉 데이터 수집 (Chronos-2 다변량 입력용)"""
        df = yf.Ticker(self.symbol).history(period=period, interval='1d')
        if df.empty:
            raise ValueError(f"No data found for {self.symbol}")
        return df

    @staticmethod
    def auto_period(forecast_steps: int) -> str:
        """forecast_steps 기준 적정 컨텍스트 기간 자동 계산 (약 5배 비율)."""
        if forecast_steps <= 10:  return '2mo'   # ~42일 컨텍스트
        if forecast_steps <= 20:  return '4mo'   # ~84일 컨텍스트
        if forecast_steps <= 30:  return '6mo'   # ~126일 컨텍스트
        if forecast_steps <= 60:  return '1y'    # ~252일 컨텍스트
        return '2y'

    def prepare_multivariate_df(self, period: str = None, forecast_steps: int = 30):
        """
        Chronos-2 / Moirai 입력용 다변량 컨텍스트 DataFrame.
        Target: Close / Covariates: volume_norm, hl_range=(H-L)/C
        period: yfinance 기간 문자열 (예: '3mo', '6mo', '1y').
                None이면 forecast_steps에 맞춰 자동 계산.
        """
        if period is None:
            period = self.auto_period(forecast_steps)
        df = self.fetch_daily(period=period)
        news = self.get_news()

        # predict_df는 timezone-naive timestamp 필요
        idx = df.index.tz_convert(None) if df.index.tz is not None else df.index
        vol_mean = df['Volume'].mean() or 1.0

        context_df = pd.DataFrame({
            'id': self.symbol,
            'timestamp': idx,
            'target': df['Close'].values,
            'volume_norm': (df['Volume'] / vol_mean).values,
            'hl_range': ((df['High'] - df['Low']) / df['Close']).values,
        })

        return {
            'context_df': context_df,
            'current_price': float(df['Close'].iloc[-1]),
            'news': news,
        }

    def prepare_all(self):
        """모델 입력용 데이터 묶음 생성 (Chronos v1 / 감성분석용)"""
        df = self.fetch_price_data()
        news = self.get_news()

        # 최근 50개 데이터 (Chronos v1 입력용)
        price_context = df['Close'].values[-50:]

        # 변동성 계산 (표준편차)
        volatility = df['Close'].pct_change().std()

        return {
            'price_context': price_context,
            'current_price': df['Close'].iloc[-1],
            'news': news,
            'volatility': 0 if np.isnan(volatility) else volatility
        }