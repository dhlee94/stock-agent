# Memento AI Agent: Stock Expert Edition 🧠

실시간 뉴스 감성 분석(FinBERT)과 시계열 예측(Chronos-2 / Moirai 2.0)을 결합한 하이브리드 주식 분석 에이전트입니다.

## 🚀 Key Features
- **🤖 Dual Forecasting**: Amazon Chronos-2(다변량 시계열)와 Salesforce Moirai 2.0을 독립 신호로 병행 운용, 에이전트가 두 예측의 합의/불일치를 판단.
- **📈 Multivariate Context**: Chronos-2는 종가(Close) + 정규화 거래량(volume_norm) + 일중 변동성((H-L)/C) 3개 변수를 동시에 입력해 단변량 대비 풍부한 컨텍스트 제공.
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

# 예측 모델 선택 (기본값 그대로 사용 가능)
CHRONOS_MODEL=amazon/chronos-2          # v2 다변량 (기본값)
MOIRAI_ENABLED=false                    # true로 설정 시 Moirai 2.0 활성화 (비상업적 용도)
MOIRAI_MODEL=Salesforce/moirai-2.0-R-small
```

### 2. Docker로 실행 (추천)
```bash
# 스케줄러(텔레그램 리포트)만 실행 — 디폴트
docker compose up -d --build

# WebUI까지 함께 실행 (포트 8000)
docker compose --profile web up -d --build
```
WebUI(`app` 서비스)는 `web` 프로파일에 묶여 있어 명시적으로 켜야 뜹니다.
스케줄러는 단독 실행되며 web 서비스에 의존하지 않습니다.

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
- `src/stock-price-predictor/`: Chronos-2 / Moirai 2.0 + FinBERT AI 모델 로직
- `src/tools/`: 주가 조회, 뉴스 검색, 기술적 분석 등 핵심 툴셋

## 🤖 Forecasting Models

| 모델 | 버전 | 입력 | 라이선스 | 기본값 |
|------|------|------|---------|--------|
| [Chronos-2](https://huggingface.co/amazon/chronos-2) | v2 | 다변량 (Close + Volume + H-L range) | Apache 2.0 | ✅ |
| [Chronos-Bolt](https://huggingface.co/amazon/chronos-bolt-small) | v1.x | 단변량 (Close) | Apache 2.0 | - |
| [Moirai 2.0](https://huggingface.co/Salesforce/moirai-2.0-R-small) | 2.0 | 단변량 (Close) | CC-BY-NC-4.0 | 비활성 |

> **Moirai 2.0**은 비상업적 연구 목적으로만 사용 가능합니다. `.env`에서 `MOIRAI_ENABLED=true`로 활성화하세요.

## ⚖️ License
MIT License
