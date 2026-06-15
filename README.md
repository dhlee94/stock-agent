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
- **MCP Session Singleton**: subprocess를 앱 수명 동안 유지하여 초기화 비용 최소화

## Quick Start

### 1. Requirements
```bash
pip install -r requirements.txt
playwright install --with-deps chromium
```

### 2. 환경 변수 설정
`.env.example`을 복사하여 `.env`를 생성하고 API 키를 입력합니다.
```bash
cp .env.example .env
```

### 3. 서버 실행
```bash
# MCP Server (Terminal 1)
python src/mcp_server.py

# Web UI (Terminal 2)
python src/web/app.py
```

## Architecture

```plaintext
User Query
    ↓
Intent Extractor — subject, intent_class, search_keywords 추출
    ↓
Planner          — MCP 툴 호출 플랜 생성 (섹터 쿼리 시 Top-down 고정 플랜)
    ↓
Executor Loop (MAX_GLOBAL_ITER=3)
  ├─ stock_news / stock_news_sentiment  →  News Analyst
  ├─ stock_technical                    →  Technical Analyst
  └─ 그 외                              →  Generic Executor
    ↓
Summarizer  →  Reflector  →  최종 한국어 리포트
    ↓
Episodic/Semantic Memory 저장 (다음 쿼리에 활용)
```

## Project Structure

```plaintext
src/
├── agent_client.py       # 멀티-에이전트 파이프라인 (핵심)
├── mcp_server.py         # MCP 툴 서버 (주가/뉴스/리스크 등)
├── config.py             # 환경변수 및 per-agent 모델/provider 설정
├── database.py           # SQLite (메모리, 설정)
├── stock_tool.py         # FinBERT 래퍼
├── memory_store.py       # Episodic / Semantic / Procedural Memory
├── driver_memory.py      # 종목별 역사적 변동 주도 요인 분석
├── risk_manager.py       # 목표가 / 손절가 / 리스크-리워드 계산
├── prompts/              # 에이전트별 시스템 프롬프트
├── tools/                # MCP 도구 구현체
│   ├── stock/            # 주가, 뉴스, 재무, 기술적 분석 등
│   ├── crawl.py          # URL 크롤링
│   └── search.py         # 웹 검색
├── web/                  # FastAPI 웹 서버 (port 8000)
├── scheduler/            # 텔레그램 일일 다이제스트
└── stock-price-predictor/
    ├── main.py           # StockBrain (FinBERT sentiment)
    └── predictor_src/    # 데이터 로더, 모델 유틸리티
```

## License
MIT License
