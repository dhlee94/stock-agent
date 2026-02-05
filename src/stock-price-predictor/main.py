import torch
import sys
import os
#system 경로 설정
sys.path.append(os.getcwd())
os.environ["USE_TORCH"] = "1"              # HuggingFace가 PyTorch만 찾도록 강제
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"   # TF 로그 완전 차단

import time
import argparse
import numpy as np
from datetime import datetime
import pytz
from src.data.loader import StockDataLoader
from src.models.fusion import MultimodalFusion
from src.utils.gatekeeper import SignalGatekeeper
from src.visualization.interpret import visualize_attention
from chronos import ChronosPipeline
from transformers import AutoTokenizer, AutoModelForSequenceClassification

class StockBrain:
    def __init__(self, ticker_symbol, ticker_name, market_type):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"🧠 {ticker_name} ({ticker_symbol}) 분석 시스템 기동 중... (Device: {self.device})")

        # 1. Pre-trained 모델 로드
        # Chronos (시계열)
        self.chronos = ChronosPipeline.from_pretrained(
            "amazon/chronos-t5-small",
            device_map=self.device,
            dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32
        )
        # FinBERT (NLP)
        self.fb_tokenizer = AutoTokenizer.from_pretrained("ProsusAI/finbert")
        self.finbert = AutoModelForSequenceClassification.from_pretrained("ProsusAI/finbert").to(self.device)
        
        # 2. 커스텀 컴포넌트 초기화
        self.loader = StockDataLoader(ticker_symbol, ticker_name, market_type)
        # Fusion 레이어: 768(BERT) + 50(Price Window) -> Output
        self.fusion = MultimodalFusion(text_dim=768, price_dim=50).to(self.device)
        self.gatekeeper = SignalGatekeeper(window_size=10, threshold=0.1) # Threshold 낮춤 (테스트용)
        
        # 최종 판단용 Linear Layer (단순화)
        self.classifier = torch.nn.Linear(128, 1).to(self.device)
        self.market_type = market_type

    def extract_features(self, news_list, price_context):
        """특징 추출"""
        # A. 뉴스 특징 (FinBERT)
        inputs = self.fb_tokenizer(news_list, return_tensors="pt", padding=True, truncation=True, max_length=512).to(self.device)
        with torch.no_grad():
            outputs = self.finbert(**inputs, output_hidden_states=True)
            # 마지막 Hidden State의 CLS 토큰 평균 사용
            text_features = outputs.hidden_states[-1][:, 0, :].mean(dim=0, keepdim=True) # (1, 768)
        
        # B. 주가 특징 (Normalization)
        p_mean = price_context.mean()
        p_std = price_context.std() + 1e-6
        price_norm = (price_context - p_mean) / p_std
        price_features = torch.tensor(price_norm, dtype=torch.float32).unsqueeze(0).to(self.device) # (1, 50)
        
        return text_features, price_features
    
    def run_analysis(self):
        if self.market_type == "US":
            tz = pytz.timezone('US/Eastern')
            currency_symbol = "$"
            price_fmt = ",.2f"
        else:
            tz = pytz.timezone('Asia/Seoul')
            currency_symbol = "₩"
            price_fmt = ",.0f"
          
        now = datetime.now(tz)
        print(f"\n{'='*60}")
        print(f"🕒 Market Time {self.market_type}: {datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')}")

        try:
            # 1. 데이터 준비
            prep = self.loader.prepare_all()            
            # 2. STL 분해 분석
            stl = self.loader.get_stl_features(self.loader.fetch_price_data())
            
            # 3. Multimodal Fusion 예측
            text_feat, price_feat = self.extract_features(prep['news'], prep['price_context'])
            
            with torch.no_grad():
                fused_vector = self.fusion(text_feat, price_feat)
                # 점수 산출 (-infinity ~ +infinity) -> Sigmoid로 0~1 확률 변환
                score = torch.sigmoid(self.classifier(fused_vector)).item()
                is_model_bullish = score > 0.5

            # 4. Chronos 단독 예측 (참조용)
            context_tensor = torch.tensor(prep['price_context'])
            forecast = self.chronos.predict(context_tensor, 5) # 5 step 예측
            chronos_pred = forecast[0].quantile(0.5).item()
            
            # 6. 결과 출력
            can_trade = self.gatekeeper.can_trade()
            cur_price = prep['current_price']
            
            print(f"📈 Current Price: {currency_symbol}{cur_price:{price_fmt}}") 
            print(f"📰 Headlines: {prep['news'][0][:60]}... (Total {len(prep['news'])})")
            
            if stl:
                trend = stl['trend']
                direction = "UP 📈" if trend > cur_price else "DOWN 📉"
                print(f"📉 [STL Trend]: {direction} (Value: {currency_symbol}{trend:{price_fmt}})")
            
            print(f"🤖 [AI Score]: {score:.4f} ({'Bullish' if is_model_bullish else 'Bearish'})")
            print(f"🔮 [Chronos Forecast]: {currency_symbol}{chronos_pred:{price_fmt}}")
            
            if not can_trade:
                print("🛡️ [Gatekeeper] Blocked due to low accuracy.")
                return

            if is_model_bullish and (stl and stl['trend'] > cur_price):
                print("\n🔥 [CONCLUSION] >> STRONG BUY (AI & Trend align)")
            elif not is_model_bullish and (stl and stl['trend'] < cur_price):
                print("\n❄️ [CONCLUSION] >> STRONG SELL (Bearish alignment)")
            else:
                print("\n⚖️ [CONCLUSION] >> NEUTRAL / HOLD")

        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Stock Price Predictor')
    parser.add_argument('--ticker', type=str, default='005930.KS', help='Ticker symbol (e.g., 005930.KS, NVDA)')
    parser.add_argument('--name', type=str, default='Samsung Electronics', help='Company name')
    parser.add_argument('--market', type=str, default='KR', choices=['KR', 'US'], help='Market type (KR or US)')
    parser.add_argument('--interval', type=int, default=600, help='Loop interval in seconds (default: 600)')

    args = parser.parse_args()
    bot = StockBrain(args.ticker, args.name, market_type=args.market)
    
    print(f"\n🔄 [{args.name}] 10분 간격 자동 분석 모드 시작")
    print(f"⏱️ 인터벌: {args.interval}초")
    print("🛑 멈추려면 정지(Stop) 버튼을 누르세요.")
    try:
        while True:
            bot.run_analysis()
            print(f"\n⏳ {args.interval}초 뒤에 다시 분석합니다... (Waiting...)")
            time.sleep(args.interval)
            
    except KeyboardInterrupt:
        print("\n🛑 [사용자 중단] 분석 종료.")