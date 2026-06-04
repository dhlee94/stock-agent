# Memento AI Agent: Stock Expert Edition 🧠

실시간 뉴스 감성 분석과 시계열 예측(Moirai 2.0)을 결합한 멀티-에이전트 주식 분석 시스템입니다.  
사용자의 자연어 질문을 받아 Intent Extraction → Planning → Execution → Reflection 파이프라인으로 전문가 수준의 한국어 투자 리포트를 생성합니다.

## 🚀 Key Features

- **🤖 Multi-Agent Pipeline**: Intent Extractor → Planner → Executor (뉴스/기술/예측 전문 Agent) → Summarizer → Reflector
- **📈 Moirai 2.0 Primary Forecaster**: Salesforce Moirai 2.0으로 가격 예측, Chronos-2는 보조 신호 (선택)
- **🔄 Prediction Feedback Loop**: 5~9일 예측을 DB에 저장하고, 목표일 이후 yfinance로 자동 채점 → Planner가 적중률 기반으로 context_period 선택
- **🏭 Sector Top-Down Analysis**: "바이오주 어때?" 같은 섹터 쿼리 시 stock_sector → stock_compare → winner 집중 분석
- **📊 Peer Analysis**: 경쟁사 상관관계 분석으로 Reflector 신호 교차 검증
- **⚡ MCP Session Singleton**: subprocess를 앱 수명 동안 유지, Moirai 콜드 스타트 최초 1회로 제한
- **🐳 Docker Ready**: 컨테이너 즉시 실행 가능
- **📢 Telegram Digest**: 워치리스트 종목 일일 리포트 자동 전송

## 🏗️ Architecture

```
사용자 쿼리 (자연어)
    ↓
Intent Extractor  — subject, intent_class, forecast_horizon, search_keywords 추출
    ↓
Planner          — MCP 툴 호출 플랜 생성 (섹터 쿼리 시 Top-down 고정 플랜)
    ↓
Executor Loop (MAX_ITER=2, MAX_STEPS_PER_ITER=8)
  ├─ stock_news / stock_news_sentiment  →  News Analyst
  ├─ stock_technical                    →  Technical Analyst
  ├─ stock_moirai_forecast              →  Forecast Interpreter
  └─ 그 외                              →  Generic Executor
    ↓
Summarizer  →  Reflector  →  최종 한국어 리포트
    ↓
Episodic/Semantic Memory 저장 (다음 쿼리에 활용)
```

## 🛠️ Quick Start

### 1. 환경 설정 (.env)

`.env.example`을 복사해서 API 키를 설정합니다.

```bash
cp .env.example .env
```

주요 설정:

```env
# LLM Provider (anthropic 권장)
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=your_api_key_here

# 에이전트별 모델 개별 지정 (미설정 시 LLM_MODEL 사용)
# PLANNER_MODEL=claude-sonnet-4-6
# REFLECTOR_MODEL=claude-sonnet-4-6
# EXECUTOR_MODEL=claude-haiku-4-5-20251001

# Moirai 2.0 (기본 활성, 비상업적 용도 — CC-BY-NC-4.0)
MOIRAI_ENABLED=true
MOIRAI_MODEL=Salesforce/moirai-2.0-R-small

# Chronos-2 (보조 신호, 기본 비활성 — Apache 2.0)
CHRONOS_ENABLED=false

# 텔레그램 다이제스트
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
SCHEDULER_WATCHLIST=005930.KS,000660.KS,NVDA
```

### 2. Docker로 실행 (권장)

```bash
# 이미지 빌드
docker compose build

# 스케줄러만 실행 (텔레그램 리포트)
docker compose up -d

# Web UI 포함 실행 (http://localhost:8000)
docker compose --profile web up -d
```

> **주의**: 코드 변경 후 반드시 컨테이너 재생성 필요  
> `docker restart`는 이미지를 교체하지 않습니다.
> ```bash
> docker compose --profile web up -d --build
> ```

### 3. 로컬 실행

```bash
pip install -r requirements.txt

# Web UI
python -m web.app

# 스케줄러 즉시 실행 (텔레그램 전송)
python -m scheduler.main --once
```

## 📁 Project Structure

```
src/
├── agent_client.py       # 멀티-에이전트 파이프라인 (핵심)
├── mcp_server.py         # MCP 툴 서버 (주가/뉴스/예측/리스크 등)
├── config.py             # 환경변수 및 per-agent 모델 설정
├── database.py           # SQLite (예측 로그, 메모리, 설정)
├── memory_store.py       # Episodic / Semantic / Procedural Memory
├── prompts/              # 에이전트별 시스템 프롬프트
│   ├── intent_extractor/ # 쿼리 구조화 (forecast_horizon 포함)
│   ├── planner/          # 툴 호출 플랜 생성
│   ├── executor/         # 툴 결과 해석
│   ├── news_analyst/     # 뉴스/감성 신호 전문 해석
│   ├── technical_analyst/# 기술적 지표 전문 해석
│   ├── forecast_interpreter/ # 예측 결과 근거 해설
│   ├── summarizer/       # 최종 한국어 리포트 생성
│   └── reflector/        # 품질 검토 및 재실행 판단
├── tools/stock/          # 주가/기술분석/뉴스/예측 툴
├── web/                  # FastAPI 웹 서버 (port 8000)
└── scheduler/            # 텔레그램 일일 다이제스트
```

## 🤖 Forecasting Models

| 모델 | 역할 | 라이선스 | 기본값 |
|------|------|---------|--------|
| [Moirai 2.0-R-small](https://huggingface.co/Salesforce/moirai-2.0-R-small) | Primary — 가격 예측, 예측 피드백 루프 | CC-BY-NC-4.0 | ✅ 활성 |
| [Chronos-2](https://huggingface.co/amazon/chronos-2) | Secondary — 보조 신호 | Apache 2.0 | 비활성 |

> **Moirai 2.0**은 비상업적 연구 목적으로만 사용 가능합니다.

## 🔮 Prediction Feedback Loop

에이전트가 `forecast_steps < 10`인 단기 예측을 수행할 때마다 `prediction_log` 테이블에 자동 저장됩니다.  
스케줄러 실행 시 목표일이 지난 예측을 yfinance로 채점하여 방향 적중률을 누적합니다.  
Planner는 `get_forecast_accuracy` 툴로 ticker별 적중률을 조회하여 최적 `context_period`를 선택합니다.

```bash
# 수동 채점 실행
python -m scheduler.main --once
```

## ⚖️ License

MIT License
