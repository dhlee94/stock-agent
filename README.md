# 🤖 Stock Expert AI Agent

> **AI 기반 주식 전문가 에이전트**  
> Memento 멀티모달 분석 + 리스크 관리 + 다국어 지원

---

## ✨ Features

- 🧠 **Memento Architecture**: [논문](https://arxiv.org/abs/2401.08017) 기반 Planner / Executor / Summarizer / Reflector 구조
- 📊 **Technical Analysis**: RSI, MACD, Bollinger Bands, Moving Averages
- 📈 **Fundamental Analysis**: PER, PBR, ROE, EPS, 재무제표
- 🤖 **AI Prediction**: Chronos 시계열 + 뉴스 기반 멀티모달 예측
- 📰 **Multi-language News**: 한국/미국 주식 자동 감지, 영어→한글 분석
- 🎯 **Risk Management**: Target Price, Stop-loss, Risk/Reward 자동 계산
- 💾 **Memory System**: DriverMemory (주가 변동 원인), ProceduralMemory (성공 패턴), Semantic Memory
- 🔍 **Self-Reflection**: Reference Proxy 기반 논리 검증 및 자동 수정
- 📱 **Web Dashboard / Web Client**: 모바일/PC 반응형 UI (Streamlit / FastAPI)

---

## 🚀 Quick Start

### 1. Setup

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Mac / Linux
source venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Configure API Key

```bash
cp .env.example .env   # Windows PowerShell: copy .env.example .env
# .env에 LLM / 데이터 관련 API 키를 입력하세요.
```

> API 키가 하나도 없을 경우, 에이전트는 **MOCK 모드**로 동작하며 간단한 데모 응답만 반환합니다.  
> 실제 투자 분석에는 최소 1개의 LLM API 키 설정을 권장합니다.

### 3. Run

#### 🎛️ 관리자 대시보드 (Admin)

데이터 관리, 메모리 열람, 에이전트 설정을 위한 제어판입니다.

```bash
streamlit run src/dashboard/app.py
```

**접속**: `http://localhost:8501`

#### 📱 사용자 웹 서비스 (Client)

일반 사용자용 AI 채팅 + 종합 주식 분석 웹 인터페이스입니다.

```bash
python src/web/app.py
```

**접속**: `http://localhost:8000`

#### 💻 CLI Agent

```bash
python main.py "삼성전자 분석해줘"
python main.py "NVIDIA 전망 분석해줘"
```

#### 🧪 Debug / Flow Test

```bash
python test_agent_flow.py "SK하이닉스 분석"
```

#### 🇰🇷 데이터 품질 검증 (KR 전용)

```bash
python verify_korea_data.py "005930.KS"
```

---

## 🏗️ Architecture (High Level)

상세한 아키텍처는 `docs/ARCHITECTURE.md`를 참고하세요.

```
┌─────────────────────────────────────────────────────────────┐
│                     📱 Web UI / CLI                         │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                   🧠 PLANNER (LLM)                          │
│  - 사용자 요청 분석                                          │
│  - DriverMemory / Semantic Memory 조회                      │
│  - 실행 계획(JSON) 수립                                     │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                   ⚡ EXECUTOR (LLM)                         │
│  MCP Tools: price, technical, news, peers, risk, predict…  │
│  - ProceduralMemory 기반 도구 사용 패턴 재활용             │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                   📊 SUMMARIZER (LLM)                       │
│  - 최종 한국어 리포트 생성                                   │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│               🔍 REFLECTOR (Self-Check LLM)                │
│  - Reference Proxy(동종 업종 대표주)와 일관성 검증          │
│  - 리스크 허용도 기반 톤 보정                               │
└─────────────────────────┴───────────────────────────────────┘
```

---

## 📊 Data Source Architecture (Hybrid)

최적의 데이터 품질을 위해 **국내/해외 이원화 아키텍처**를 사용합니다.

| Region | Data Type | Source | Description |
|--------|-----------|--------|-------------|
| **KR** 🇰🇷 | Price | `FinanceDataReader` | KRX/Naver 기반 정확한 수정주가 |
| | Financials | `PyKRX` | PER, PBR, BPS 등 핵심 투자지표 크롤링 |
| | Corporate | `yfinance` | 기업 개요, 섹터 정보 보완 |
| **US** 🇺🇸 | All | `yfinance` | 글로벌 표준 데이터 |

> **자동 번역 레이어**: `PyKRX`의 한글 데이터(예: "영업이익")는 내부적으로 영어 키(`operating_income`)로 자동 매핑되어 LLM이 일관되게 분석합니다.

---

## 📂 Project Structure

```
agent/
├── main.py                    # CLI 진입점 (에이전트 실행)
├── test_agent_flow.py         # 🧪 에이전트 플로우 디버그 스크립트
├── verify_korea_data.py       # 🇰🇷 한국 주식 데이터 품질 검증 스크립트
├── requirements.txt
├── .env.example               # 환경변수 템플릿
├── memory_store.json          # 임베딩 메모리 저장소
├── data/
│   ├── memento.db             # SQLite DB (설정, 메모리, 사용 통계)
│   └── sector_competitors.json# 섹터별 기본 경쟁사 맵
├── docs/
│   ├── ARCHITECTURE.md        # 상세 아키텍처 문서
│   └── img/                   # 다이어그램 이미지
└── src/
    ├── agent_client.py        # 🧠 Memento Agent (Planner/Executor/Reflector)
    ├── mcp_server.py          # MCP Tool Server
    ├── database.py            # SQLite 연결 & 설정/통계 유틸
    ├── memory_store.py        # Embedding 기반 메모리
    ├── driver_memory.py       # 📈 Driver Memory (주가 변동 원인)
    ├── risk_manager.py        # 🎯 Risk Management 계산 로직
    ├── stock_tool.py          # 🤖 Chronos + 뉴스 융합 예측 래퍼
    ├── dashboard/             # 🎛️ 관리자 대시보드 (Streamlit)
    │   ├── app.py             # 대시보드 메인
    │   └── pages/             # Market Data, Memory, Settings
    ├── web/                   # 📱 사용자 웹 서비스 (FastAPI)
    │   ├── app.py             # FastAPI 서버
    │   ├── templates/         # HTML 템플릿
    │   └── static/            # CSS / 정적 리소스
    ├── tools/                 # MCP Tools
    │   ├── stock/             # 📊 Stock Tools
    │   │   ├── price.py       # 실시간 주가
    │   │   ├── chart.py       # 차트 데이터
    │   │   ├── financials.py  # 재무제표
    │   │   ├── news.py        # 뉴스 (다국어 지원)
    │   │   ├── technical.py   # 기술적 분석
    │   │   ├── market_utils.py# 🌍 시장 감지 (KR/US)
    │   │   ├── compare.py     # 종목 비교
    │   │   ├── sector.py      # 섹터 분석
    │   │   ├── predictor.py   # AI 예측
    │   │   └── peer_analysis.py# 📊 Peer Group 분석 (STL Trend)
    │   ├── search.py          # 웹 검색
    │   ├── crawl.py           # 웹 크롤러
    │   ├── document.py        # 문서 읽기
    │   ├── memory.py          # 메모리 유틸 MCP 래퍼
    │   ├── calc.py            # 수치 계산
    │   ├── image.py           # 이미지 처리
    │   ├── video.py           # 비디오 관련 유틸
    │   └── executor.py        # MCP 도구 실행 유틸
    └── stock-price-predictor/ # Chronos 기반 시계열 예측 모듈
        ├── main.py
        ├── trainer.py
        └── predictor_src/...
```

---

## 📈 Available Tools (MCP)

MCP 서버(`src/mcp_server.py`)를 통해 LLM이 호출할 수 있는 도구 목록입니다.

| Tool | Description |
|------|-------------|
| `stock_price` | 실시간 주가, 등락률, 거래량 |
| `stock_chart` | OHLCV 차트 데이터 |
| `stock_technical` | RSI, MACD, 볼린저밴드, MA |
| `stock_news` | 종목/시장 뉴스 (KR/US 자동 감지) |
| `stock_financials` | PER, PBR, ROE, 배당 등 재무지표 |
| `stock_compare` | 다중 종목 비교 |
| `stock_sector` | 섹터별 분석 |
| `stock_ai_predict` | 🤖 Chronos + 뉴스 멀티모달 예측 |
| `analyze_drivers` | 📈 과거 주가 변동 원인 분석 (Driver Memory) |
| `analyze_peers` | 📊 Peer Group 분석 (뉴스 Entity + STL Trend) |
| `calculate_risk` | 🎯 Target Price, Stop-loss, Risk/Reward |
| `web_search` | 일반 웹 검색 |
| `web_crawl` | URL 크롤링 & 콘텐츠 추출 |
| `run_python` | 간단한 Python 코드 실행 |
| `calc_math` | 수치 계산 유틸 |
| `read_file` | 문서 파일 읽기 |
| `save_memory` | Trajectory/피드백 저장 |

---

## 📊 Peer Analysis System

뉴스에서 경쟁사를 찾지 못하면 **LLM이 자동으로 Industry Benchmark를 추론**합니다.

```
"삼성전자 분석" → 뉴스 탐색 → 0건
                ↓
    🤖 LLM: "경쟁사는?" → [SK하이닉스, 마이크론]
                ↓
    STL Trend 상관관계 계산 → Reference Proxy 선정
                ↓
    Reflector 검증 (Confidence: High / Medium / Low)
```

**사용자 지정 비교 예시:**

```bash
# "SK하이닉스랑 비교해서" 입력 시 직접 비교
"삼성전자 분석해줘 SK하이닉스랑 비교해서"
```

---

## 🎯 Risk Management Output

분석 결과에 다음 지표가 포함됩니다:

```
🎯 Target Price: 170,588원 (+8.17%)
🛑 Stop-loss: 146,661원 (-7.0%)
⚖️ Risk/Reward: 1.17:1 (Entry Rating: GOOD)
```

| Rating | Risk/Reward | 의미 |
|--------|-------------|------|
| EXCELLENT | ≥ 2.0 | 매우 좋은 진입 타이밍 |
| GOOD | ≥ 1.5 | 좋은 기회 |
| FAIR | ≥ 1.0 | 보통 |
| POOR | < 1.0 | 위험 대비 수익 낮음 |

---

## 🌍 Multi-language Support

| 주식 | 시장 | 뉴스 검색 | 최종 출력 |
|------|------|----------|----------|
| 삼성전자 (005930.KS) | 🇰🇷 KR | 한국어 | 한국어 |
| NVIDIA (NVDA) | 🇺🇸 US | 영어 | 한국어 |
| Apple (AAPL) | 🇺🇸 US | 영어 | 한국어 |

---

## 🔧 Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `LLM_PROVIDER` | No | `groq` (기본), `gemini`, `openai` |
| `GROQ_API_KEY` | Yes* | Groq API 키 (무료, Llama 3.3 70B) |
| `GEMINI_API_KEY` | Yes* | Gemini API 키 (무료, Gemini 2.0 Flash) |
| `OPENAI_API_KEY` | No | OpenAI API 키 (유료, GPT-4o 등) |

*최소 하나의 LLM API 키가 있으면 실제 LLM 모드로 동작하며, 모두 없으면 MOCK 모드로 동작합니다.

---

## 📚 References

- [Memento Paper](https://arxiv.org/abs/2401.08017) - Self-Refinement 에이전트 아키텍처
- [MCP Protocol](https://modelcontextprotocol.io) - Model Context Protocol
- [Chronos Forecasting](https://github.com/amazon-science/chronos-forecasting) - 시계열 예측
- [yfinance](https://github.com/ranaroussi/yfinance) - 주식 데이터
- [FinanceDataReader](https://github.com/FinanceData/FinanceDataReader) - 한국 주식 가격
- [PyKRX](https://github.com/sharebook-kr/pykrx) - 한국 주식 재무지표

---

⚠️ **Disclaimer**: 본 시스템의 분석은 참고용이며, 투자 결정은 본인 책임입니다.
