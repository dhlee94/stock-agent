# Memento AI Agent: Stock Expert Edition 🧠

실시간 뉴스 감성 분석(FinBERT)과 시계열 예측(Chronos)을 결합한 하이브리드 주식 분석 에이전트입니다.

## 🚀 Key Features
- **🤖 Multimodal AI Prediction**: Amazon Chronos(시계열)와 FinBERT(뉴스 감성)를 결합한 정밀 예측.
- **📊 Peer Analysis**: STL 분해(Seasonal-Trend-Loess)를 통한 경쟁사 간 트렌드 상관관계 분석.
- **🔎 Real-time Search**: DuckDuckGo를 활용한 최신 시장 이슈 추적.
- **💻 Interactive Dashboard**: Streamlit 기반의 실시간 모니터링 및 메모리 뷰어.
- **🐳 Docker Ready**: 복잡한 환경 설정 없이 컨테이너로 즉시 실행 가능.
- **📢 Telegram Alert**: 일일 분석 리포트 자동 전송 기능.

## 🛠️ Quick Start

### 1. 환경 설정 (.env)
`.env` 파일에 필요한 API 키를 설정합니다. (Gemini, Groq, OpenAI 등 선택 가능)
```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_api_key_here
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
SCHEDULER_WATCHLIST=005930.KS,NVDA
```

### 2. Docker로 실행 (추천)
```bash
docker-compose up --build
```

### 3. 로컬 실행
```bash
# 의존성 설치
pip install -r requirements.txt
playwright install chromium

# 대시보드 실행
streamlit run src/dashboard/app.py

# 텔레그램 리포트 즉시 전송 테스트
python3 src/scheduler/main.py --once
```

## 📁 Project Structure
- `src/dashboard/`: Streamlit 대시보드 앱
- `src/web/`: Flask 기반 웹 서비스
- `src/scheduler/`: 일일 리포트 스케줄러 (Telegram 전송)
- `src/stock-price-predictor/`: Chronos + FinBERT AI 모델 로직
- `src/tools/`: 주가 조회, 뉴스 검색, 기술적 분석 등 핵심 툴셋

## ⚖️ License
MIT License
