# Memento AI Agent: Stock Expert Edition

정밀한 시장 데이터 분석과 뉴스 해석을 결합한 멀티-에이전트 주식 분석 시스템입니다.  
사용자의 자연어 질문을 받아 **Global Planning → 병렬 수집 → Critic·Defense·Judge 자기교정 → 통합·요약** 파이프라인으로 전문가 수준의 한국어 투자 리포트를 생성합니다.

전체 코드 흐름의 상세 설명은 [`ARCHITECTURE_FLOW.txt`](ARCHITECTURE_FLOW.txt)를 참고하세요.

## Key Features

- **Multi-Agent Pipeline**: Global Planner → (병렬) Sub-Planner → Executor / News·Technical Analyst → Reflector ↔ Planner Defense ↔ Judge → Summarizer
- **Self-Correcting Loop**: Reflector(비평) ↔ Planner(방어) ↔ Judge(심판) 삼자 토론으로 분석을 자기교정 (최대 `MAX_GLOBAL_ITER=3` 라운드)
- **Tiered Analysis**: Tier-1 병렬 수집 후, 단일 종목은 Tier-2 통합 단계에서 뉴스 촉매·기술적 레벨을 밸류에이션(DCF)에 정량 반영
- **Hallucination Guards**: 티커 상장정보 교차검증 + `price × shares ≈ 시가총액` 산술 앵커 + 분석 프롬프트에 현재 날짜(KST) 주입
- **Per-Agent Provider Mixing**: 에이전트별로 다른 LLM Provider/모델 혼용 가능 (모델명에서 provider 자동 감지)
- **3-Layer Memory**: Episodic(궤적) / Semantic(교훈, 주·월·연 압축 롤오버) / Procedural(툴 팁)
- **Deadline-Aware**: 웹 요청 타임아웃 전 시간예산(`FLOW_TIME_BUDGET_SEC`)을 지켜 부분 리포트라도 반환
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
# Web UI (FastAPI, port 8000)
python src/web/app.py

# 텔레그램 일일 다이제스트 (선택) — cron 스케줄 실행
python -m src.scheduler.main          # 매일 지정 시각 실행
python -m src.scheduler.main --once   # 1회만 실행
```
> MCP 툴 서버(`src/mcp_server.py`)는 에이전트가 subprocess로 자동 기동·유지하므로 별도로 실행할 필요가 없습니다.

## Architecture

```plaintext
User Query
    ↓
Global Planner ──── 질문 파싱 → { subject, subtasks[] } + 티커 상장정보 교차검증
    ↓
_run_flow (오케스트레이션, 시간예산 FLOW_TIME_BUDGET_SEC)
  │
  ├─ market_facts 앵커 (price × shares ≈ 시총, 52주 범위 산술검증)
  │
  ├─ [Tier-1] subtasks 병렬 실행 (Semaphore 3)
  │     각 subtask: Sub-Planner → MCP 툴 호출 → 해석
  │        ├─ stock_news       →  News Analyst (+ sentiment guardrail)
  │        ├─ stock_technical  →  Technical Analyst
  │        └─ 그 외            →  Generic Executor
  │
  ├─ 자기교정 루프 (MAX_GLOBAL_ITER=3, deadline/no_progress 가드)
  │     Reflector(비평) ─approved?─→ 탈출
  │        └ 미승인 → Planner Defense → Judge 심판
  │                     ├ critic 승 → 다음 라운드 정제
  │                     └ planner 승 → 탈출 (미해결점 기록)
  │
  ├─ [Tier-2] 단일 종목이면 통합 subtask 1회 (촉매 반영 DCF 재실행 등)
  │
  └─ Summarizer → 한국어 리포트 (+ 미해결 공백을 한계로 명시)
    ↓
Episodic Memory 저장 (임베딩 dedup, 다음 쿼리에 활용)
```

## Project Structure

```plaintext
src/
├── agent_client.py       # 멀티-에이전트 파이프라인 (핵심: _run_flow)
├── mcp_server.py         # MCP 툴 서버 (주가/뉴스/재무/기술/리스크 등)
├── config.py             # 환경변수 및 per-agent 모델/provider 설정
├── database.py           # SQLite (메모리, 설정)
├── memory_store.py       # Episodic / Semantic / Procedural Memory
├── driver_memory.py      # 종목별 역사적 변동 주도 요인 분석
├── risk_manager.py       # 목표가 / 손절가 / 리스크-리워드 계산
├── prompts/              # 에이전트별 시스템 프롬프트 (역할별 디렉터리)
├── tools/                # MCP 도구 구현체
│   ├── stock/            # 주가, 차트, 재무, DCF, 뉴스, 기술, 섹터, 비교, 동종군
│   ├── crawl.py          # URL 크롤링
│   ├── search.py         # 웹 검색
│   ├── executor.py       # 파이썬 코드 실행
│   ├── calc.py           # 수식 계산
│   ├── document.py       # 문서 읽기
│   └── memory.py         # 메모리 저장 툴
├── web/                  # FastAPI 웹 서버 (port 8000, 비동기 잡 패턴)
├── scheduler/            # 텔레그램 일일 watchlist 다이제스트 (APScheduler cron)
└── dashboard/            # Streamlit 대시보드 (시장 데이터 / 메모리 뷰어 / 설정)
```
> 참고: ML 가격예측(`stock-price-predictor/`)과 FinBERT 감성 래퍼(`stock_tool.py`)는
> 제거되었습니다("light mode"). 감성은 `stock_news` + News Analyst로 처리합니다.

## License
MIT License
