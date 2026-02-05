import pandas as pd
import matplotlib.pyplot as plt
from statsmodels.tsa.seasonal import STL

def perform_stl_analysis(df, column='Close', period=None):
    """
    주가 데이터를 STL 분해하여 각 성분을 반환합니다.
    수학적 모델: $Y_t = T_t + S_t + R_t$ (덧셈 모델)
    """
    if df.empty or len(df) < 10:
        return None
    
    # 시계열 데이터 추출
    series = df[column]
    
    # STL 분해 (period가 None이면 데이터 주기에 따라 자동 설정 시도)
    # 분 분해인 경우 보통 60(1시간) 또는 390(하루 장 시간) 등을 설정합니다.
    stl = STL(series, period=period, robust=True)
    result = stl.fit()
    
    return result

def get_trend_signal(stl_result):
    """최근 추세가 상승인지 하락인지 판단합니다."""
    trend = stl_result.trend
    if trend.iloc[-1] > trend.iloc[-2]:
        return "상승 추세"
    return "하락 추세"
