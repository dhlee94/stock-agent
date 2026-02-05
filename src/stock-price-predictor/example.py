import yfinance as yf
import torch
import pandas as pd
from chronos import ChronosPipeline
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from pygooglenews import GoogleNews
from datetime import datetime
import time

# 1. 모델 로드
print("모델 로딩 중 (Chronos & FinBERT)...")
# 주가 예측 모델
chronos_pipeline = ChronosPipeline.from_pretrained(
    "amazon/chronos-t5-small",
    device_map="cuda" if torch.cuda.is_available() else "cpu",
    torch_dtype=torch.bfloat16,
)

# 뉴스 감성 분석 모델 (FinBERT)
tokenizer = AutoTokenizer.from_pretrained("ProsusAI/finbert")
finbert_model = AutoModelForSequenceClassification.from_pretrained("ProsusAI/finbert")

# 2. 뉴스 감성 분석 함수
def get_news_sentiment(ticker_name):
    gn = GoogleNews(lang='ko', country='KR')
    search = gn.search(f'{ticker_name} 주가')
    news_items = search['entries'][:5] # 최신 뉴스 5개

    total_score = 0
    print(f"\n--- 최신 뉴스 분석 ({ticker_name}) ---")

    for item in news_items:
        inputs = tokenizer(item.title, return_tensors="pt", padding=True, truncation=True)
        outputs = finbert_model(**inputs)
        # 결과: [Positive, Negative, Neutral]
        probs = torch.nn.functional.softmax(outputs.logits, dim=-1)

        # 가중치 계산 (Pos: +1, Neg: -1, Neu: 0)
        score = probs[0][0].item() - probs[0][1].item()
        total_score += score

        label = "긍정" if score > 0.1 else "부정" if score < -0.1 else "중립"
        print(f"[{label}] {item.title[:50]}...")

    avg_score = total_score / len(news_items) if news_items else 0
    return avg_score

# 3. 통합 실행 함수
def run_integrated_analysis(ticker_symbol, ticker_name):
    # 한국 시간대 정의
    kst = pytz.timezone('Asia/Seoul')

    # 분석 시각 출력 부분 수정
    now_kst = datetime.now(kst)
    print(f"\n{'='*50}")
    print(f"분석 시각 (KST): {now_kst.strftime('%Y-%m-%d %H:%M:%S')}")
    # [Step 1] 뉴스 분석
    sentiment_score = get_news_sentiment(ticker_name)

    # [Step 2] 주가 데이터 수집 및 예측
    data = yf.Ticker(ticker_symbol).history(period='1d', interval='1m')
    if len(data) < 50: return

    context = torch.tensor(data['Close'].values[-50:])
    forecast = chronos_pipeline.predict(context, 5) # 5분 뒤 예측
    predicted_price = forecast[0].quantile(0.5)
    current_price = data['Close'].values[-1]

    # [Step 3] 최종 리포트 출력
    print(f"\n--- 종합 분석 결과 ---")
    print(f"현재 주가: {current_price:,.0f}원")
    print(f"모델 예측(5분 뒤): {predicted_price:,.0f}원 ({'상승' if predicted_price > current_price else '하락'})")
    print(f"뉴스 심리 점수: {sentiment_score:.2f} ({'호재 중심' if sentiment_score > 0 else '악재 중심'})")

    # [Step 4] 간단한 의사결정 로직
    if predicted_price > current_price and sentiment_score > 0.2:
        print(">> [강력 매수 신호] 차트 패턴과 뉴스 반응이 모두 긍정적입니다.")
    elif predicted_price < current_price and sentiment_score < -0.2:
        print(">> [주의 신호] 차트 하락세와 부정적 뉴스가 겹쳐 있습니다.")
    else:
        print(">> [관망] 지표가 엇갈리거나 변동성이 적습니다.")

if __name__ == "__main__":
    # 삼성전자로 테스트
    while True:
        run_integrated_analysis("005930.KS", "삼성전자")
        run_integrated_analysis("000660.KS", "SK하이닉스")
        print(f"\n10분 후 다시 분석합니다...")
        time.sleep(600) # 10분 간격 (실시간 API 제한 고려)