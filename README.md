# Memento AI Agent: Stock Expert Edition

실시간 뉴스 감성 분석과 정밀한 시장 데이터 분석을 결합한 멀티-에이전트 주식 분석 시스템입니다.  
사용자의 자연어 질문을 받아 Intent Extraction → Planning → Execution → Reflection 파이프라인으로 전문가 수준의 한국어 투자 리포트를 생성합니다.

## Key Features

- **Multi-Agent Pipeline**: Intent Extractor → Planner → Executor (뉴스/기술 전문 Agent) → Summarizer → Reflector
- **Real-time News Sentiment**: FinBERT을 활용한 시장 감성 분석
- **Sector Top-Down Analysis**: "바이오주 어때?" 같은 섹터 쿼리 시 `stock_sector → stock_compare → winner` 집중 분석
- **Peer Analysis**: 경쟁사 상관관계 분석으로 Reflector 신호 교차 검증
- **Per-Agent Provider Mixing**: 에이전트별로 다른 LLM Provider 혼용 가능 (모델명에서 자동 감지)
- **Semantic Memory Compression**: 주간/월간/연간 롤오버 시 시맨틱 메모리를 자동 압축·요약
- **MCP Session Singleton**: subprocess를 앱 수명 동안 유지, Moirai 콜드 스타트 최초 1회로 제한
- **Docker Ready**: 컨테이너 즉시 실행 가능
- **Telegram Digest**: 워치리스트 종목 일일 리포트 자동 전송

## Architecture

```
사용자 쿼리 (자연어)
    ↓
Intent Extractor  — subject, intent_class, forecast_horizon, search_keywords 추출
    ↓
Planner          — MCP 툴 호출 플랜 생성 (섹터 쿼리 시 Top-down 고정 플랜)
    ↓
Executor Loop (MAX_GLOBAL_ITER=3, configurable via .env)
  ├─ stock_news / stock_news_sentiment  →  News Analyst
  ├─ stock_technical                    →  Technical Analyst
  └─ 그 외                              →  Generic Executor
    ↓
Summarizer  →  Reflector  →  최종 한국어 리포트
    ↓
Episodic/Semantic Memory 저장 (다음 쿼리에 활용)
```

## Quick Start

### 1. 환경 설정 (.env)

`.env.example`을 복사해서 API 키를 설정합니다.

```bash
cp .env.example .env
```

주요 설정:

```env
# LLM Provider (기본 베이스라인)
LLM_PROVIDER=anthropic
LLM_MODEL=claude-haiku-4-5-20251001
ANTHROPIC_API_KEY=your_api_key_here

# 에이전트별 모델 개별 지정 — Provider 혼용 가능 (모델명에서 자동 감지)
#   claude-*  → Anthropic,  gemini-*  → Gemini,  gpt-*/o* → OpenAI,  llama-* → Groq
# 비용 티어링은 아래 "Per-Agent Provider Mixing" 섹션 참고 (호출 빈도 기준 Haiku/Sonnet/Gemini 분배)
# PLANNER_MODEL=claude-haiku-4-5-20251001
# GLOBAL_REFLECTOR_MODEL=claude-sonnet-4-6
# SUMMARIZER_MODEL=claude-sonnet-4-6

# Moirai 2.0 (기본 활성, 비상업적 용도 — CC-BY-NC-4.0)
MOIRAI_ENABLED=true
MOIRAI_MODEL=Salesforce/moirai-2.0-R-small

# Chronos-2 (보조 신호, 기본 비활성 — Apache 2.0)
CHRONOS_ENABLED=false

# Torch 디바이스 (auto: cuda→mps→cpu 순 자동 선택, Apple Silicon 네이티브만 mps 가능)
# TORCH_DEVICE=auto

# Domain 분석 글로벌 반복 횟수 (기본값 3)
# MAX_GLOBAL_ITER=3

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

## Project Structure

```
src/
├── agent_client.py       # 멀티-에이전트 파이프라인 (핵심)
├── mcp_server.py         # MCP 툴 서버 (주가/뉴스/예측/리스크 등)
├── config.py             # 환경변수 및 per-agent 모델/provider 설정
├── database.py           # SQLite (예측 로그, 메모리, 설정)
├── stock_tool.py         # FinBERT 래퍼
├── memory_store.py       # Episodic / Semantic / Procedural Memory
├── driver_memory.py      # 종목별 역사적 변동 주도 요인 분석
├── risk_manager.py       # 목표가 / 손절가 / 리스크-리워드 계산
├── prompts/              # 에이전트별 시스템 프롬프트
│   ├── intent_extractor/ # 쿼리 구조화
│   ├── planner/          # 툴 호출 플랜 생성
│   ├── executor/         # 툴 결과 해석
│   ├── news_analyst/     # 뉴스/감성 신호 전문 해석
│   ├── technical_analyst/# 기술적 지표 전문 해석
│   ├── forecast_interpreter/ # 예측 결과 근거 해설
│   ├── summarizer/       # 최종 한국어 리포트 생성
│   └── reflector/        # 품질 검토 및 재실행 판단
├── tools/
│   ├── stock/            # 주가/기술분석/뉴스/섹터/피어/비교 툴
│   ├── executor.py       # Python 코드 실행 (제한된 샌드박스)
│   ├── calc.py           # 수식 계산 (SymPy parse_expr)
│   ├── crawl.py          # URL 크롤링 (SSRF 방지)
│   └── search.py         # 웹 검색
├── web/                  # FastAPI 웹 서버 (port 8000)
├── scheduler/            # 텔레그램 일일 다이제스트
└── stock-price-predictor/
    ├── main.py           # StockBrain (FinBERT sentiment)
    └── predictor_src/    # 데이터 로더, 모델 유틸리티
```

## Prediction Feedback Loop

에이전트가 `forecast_steps <= 10`인 단기 예측을 수행할 때마다 `prediction_log` 테이블에 자동 저장됩니다.  
스케줄러 실행 시 target_date가 지난 예측을 yfinance로 채점하여 방향 적중률을 누적합니다.  
Planner는 `get_forecast_accuracy` 툴로 ticker별 적중률을 조회하여 최적 `context_period`를 선택합니다.

```bash
# 수동 채점 실행
python -m scheduler.main --once
```

## Per-Agent Provider Mixing

`.env`에서 에이전트별로 모델을 지정할 때 **모델명에서 provider를 자동 감지**합니다.  
`LLM_PROVIDER`와 무관하게 사용할 API 키만 설정하면 됩니다.

| 모델 prefix | Provider | 필요 환경변수 |
|-------------|----------|-------------|
| `claude-*` | Anthropic | `ANTHROPIC_API_KEY` |
| `gemini-*` | Gemini | `GEMINI_API_KEY` |
| `gpt-*`, `o*` | OpenAI | `OPENAI_API_KEY` |
| `llama-*` 등 | Groq | `GROQ_API_KEY` |

**비용 티어링 — 호출 빈도 기준** (Sonnet=$3/$15, Haiku=$1/$5, Gemini≈무료 per 1M):

- **고빈도** (서브태스크마다, `N × global_iter`회 호출) → **Haiku**: 절감 효과가 가장 큼
- **저빈도** (실행당 1~3회, 루프 결정 + 사용자용 최종 리포트) → **Sonnet**: 적게 불려서 유지해도 저렴
- **처리량/가공** 역할 → **Gemini Flash**

```env
LLM_PROVIDER=anthropic
LLM_MODEL=claude-haiku-4-5-20251001

# 고빈도 (per-subtask) → Haiku
PLANNER_MODEL=claude-haiku-4-5-20251001
NEWS_ANALYST_MODEL=claude-haiku-4-5-20251001
FORECAST_INTERPRETER_MODEL=claude-haiku-4-5-20251001
# 저빈도, 품질 중요 → Sonnet
GLOBAL_PLANNER_MODEL=claude-sonnet-4-6
GLOBAL_REFLECTOR_MODEL=claude-sonnet-4-6
JUDGE_MODEL=claude-sonnet-4-6
SUMMARIZER_MODEL=claude-sonnet-4-6
# 처리량 → Gemini Flash
EXECUTOR_MODEL=gemini-2.0-flash
TECHNICAL_ANALYST_MODEL=gemini-2.0-flash
LOCAL_REFLECTOR_MODEL=gemini-2.0-flash
```

> **Prompt Caching**: Anthropic 호출은 시스템 프롬프트에 `cache_control`을 적용해, 한 실행 안에서 반복되는 에이전트 호출이 캐시된 프리픽스를 ~0.1배 입력 비용으로 재사용합니다. 캐시 히트 시 `💾 cache hit` 로그가 출력됩니다. (OpenAI는 자동 캐싱, Gemini는 별도 API라 미적용)

## License

MIT License
