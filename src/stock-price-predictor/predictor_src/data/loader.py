import yfinance as yf
import pandas as pd
import numpy as np
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

    def prepare_all(self):
        """모델 입력용 데이터 묶음 생성"""
        df = self.fetch_price_data()
        news = self.get_news()
        
        # 최근 50개 데이터 (Chronos/Fusion 입력용)
        price_context = df['Close'].values[-50:]
        
        # 변동성 계산 (표준편차)
        volatility = df['Close'].pct_change().std()
        
        return {
            'price_context': price_context,
            'current_price': df['Close'].iloc[-1],
            'news': news,
            'volatility': 0 if np.isnan(volatility) else volatility
        }