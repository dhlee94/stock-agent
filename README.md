# 🤖 Stock Expert AI Agent

> **AI 기반 주식 전문가 에이전트**  
> Memento 멀티모달 분석 + 리스크 관리 + 다국어 지원

---

## ✨ Features

- 🧠 **Memento Architecture**: [논문](https://arxiv.org/abs/2512.22716) 기반 Planner/Executor/Reflector + 3중 메모리 구조
- 📊 **Technical Analysis**: RSI, MACD, Bollinger Bands, Moving Averages
- 📈 **Fundamental Analysis**: PER, PBR, ROE, EPS, 재무제표
- 🤖 **AI Prediction**: Chronos 시계열 예측
- 📰 **Multi-language News**: 한국/미국 주식 자동 감지, 영어→한글 분석
- 🎯 **Risk Management**: Target Price, Stop-loss, Risk/Reward 자동 계산
- 💾 **3-Layer Memory System**:
  - **Episodic Memory**: 과거 trajectory 저장 + 품질 기반 Memory Rewriting
  - **Semantic Memory**: Reflector가 추출한 일반화 지식 (cross-task 전이)
  - **Procedural Memory**: 도구 실행 패턴 학습 → Executor에 직접 전달
- 🔍 **Self-Reflection**: 논리적 일관성 검증 + 피드백 추출 → 메모리 자동 업데이트
- 🆓 **Autonomous Planner**: 도구 설명과 메모리만으로 자유롭게 계획 수립 (고정 워크플로우 없음)
- 📱 **Web Dashboard**: 모바일/PC 반응형 UI

---

## 🚀 Quick Start

### 1. Setup
```bash
python -m venv venv
source venv/bin/activate   # Mac/Linux
pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Configure API Key
```bash
cp .env.example .env
# Edit .env and add your API keys
```

### 3. Run

#### 🎛️ 관리자 대시보드 (Admin)
데이터 관리, 메모리 열람, 에이전트 설정을 위한 제어판입니다.
```bash
streamlit run src/dashboard/app.py
```
**접속**: http://localhost:8501

#### 📱 사용자 웹 서비스 (Client)
일반 사용자용 AI 채팅 인터페이스입니다.
```bash
python src/web/app.py
```
**접속**: http://localhost:8000

#### 💻 CLI Agent
```bash
python main.py "삼성전자 분석해줘"
python main.py "NVIDIA 전망 분석해줘"
```

#### 🧪 Debug Mode
```bash
python test_agent_flow.py "SK하이닉스 분석"
```

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     📱 Web UI / CLI                         │
└─────────────────────────┬───────────────────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
   Episodic Memory  Semantic Memory  Procedural Memory
   (past plans)    (cross-task      (tool execution
                    lessons)         patterns)
          └───────────────┬───────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                   🧠 PLANNER (LLM)                          │
│  - Episodic Memory에서 유사 계획 검색                         │
│  - Semantic Memory에서 관련 lessons 수신                      │
│  - 도구 설명만으로 자율적 계획 수립 (고정 워크플로우 없음)        │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                   ⚡ EXECUTOR                               │
│  - Procedural Memory tips를 받아 도구 결과 해석               │
│  MCP Tools: price, technical, news, risk, predict...       │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                   🔍 REFLECTOR (Self-Check + Memory Update) │
│  - 논리적 일관성 검증 (RSI < 30 인데 SELL?)                   │
│  - 피드백 추출: score(0~1) + lessons                         │
│  - Episodic Memory rewriting (더 나은 결과로 교체)            │
│  - Semantic Memory에 lessons 저장 (cross-task 전이)          │
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
├── main.py                    # CLI 진입점
├── test_agent_flow.py         # 🧪 Debug/Test script
├── requirements.txt
├── .env.example               # 환경변수 템플릿
└── src/
    ├── agent_client.py        # 🧠 Memento Agent (Planner/Executor/Reflector)
    ├── mcp_server.py          # MCP Tool Server
    ├── memory_store.py        # 3-Layer Memory (Episodic/Semantic/Procedural)
    ├── driver_memory.py       # 📈 Driver Memory (주가 변동 원인)
    ├── risk_manager.py        # 🎯 Risk Management
    ├── dashboard/             # 🎛️ 관리자 대시보드 (Streamlit)
    │   ├── app.py             # 대시보드 메인
    │   └── pages/             # 대시보드 페이지 (Market Data, Memory, Settings)
    ├── web/                   # 📱 사용자 웹 서비스 (FastAPI)
    │   ├── app.py             # FastAPI 서버
    │   ├── templates/         # HTML
    │   └── static/            # CSS
    └── tools/stock/           # 📊 Stock Tools
        ├── price.py           # 실시간 주가
        ├── chart.py           # 차트 데이터
        ├── financials.py      # 재무제표
        ├── news.py            # 뉴스 (다국어 지원)
        ├── technical.py       # 기술적 분석
        ├── market_utils.py    # 🌍 시장 감지 (KR/US)
        ├── compare.py         # 종목 비교
        ├── sector.py          # 섹터 분석
        ├── predictor.py       # AI 예측
        └── peer_analysis.py   # 📊 Peer Group 분석 (STL Trend)
```

---

## 📈 Available Tools

| Tool | Description |
|------|-------------|
| `stock_price` | 실시간 주가, 등락률, 거래량 |
| `stock_technical` | RSI, MACD, 볼린저밴드, MA |
| `stock_news` | 종목/시장 뉴스 (KR/US 자동 감지) |
| `stock_financials` | PER, PBR, ROE, 배당 등 |
| `analyze_drivers` | 📈 과거 주가 변동 원인 분석 (LLM 기반) |
| `calculate_risk` | 🎯 Target Price, Stop-loss, Risk/Reward |
| `stock_ai_predict` | 🤖 AI 예측 (Chronos) |
| `stock_compare` | 다중 종목 비교 |
| `stock_sector` | 섹터별 분석 |
| `analyze_peers` | 📊 Peer Group 분석 (STL Trend + LLM 경쟁사 탐색) |

---

## 📊 Peer Analysis System

뉴스에서 경쟁사를 찾지 못하면 **LLM이 자동으로 Industry Benchmark 추론**:

```
"삼성전자 분석" → 뉴스 탐색 → 0건
                ↓
    🤖 LLM: "경쟁사는?" → [SK하이닉스, 마이크론]
                ↓
    STL Trend 상관관계 계산 → Reference Proxy 선정
                ↓
    Reflector 검증 (Confidence: High/Medium/Low)
```

**사용자 지정 비교:**
```bash
# "SK하이닉스랑 비교해서" 입력 시 직접 비교
"삼성전자 분석해줘 SK하이닉스랑 비교해서"
```

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
| `GEMINI_API_KEY` | Yes* | Gemini API 키 (무료) |
| `OPENAI_API_KEY` | No | OpenAI API 키 (유료) |

*최소 하나의 LLM API 키 필요

---

## 💾 Memory System

| 메모리 | 저장 내용 | 역할 |
|--------|----------|------|
| **Episodic** | 과거 task trajectory (plan + result + score) | Planner에게 유사 계획 예시 제공 |
| **Semantic** | Reflector가 추출한 일반화 lessons | 다른 종목 분석에도 전이되는 패턴 |
| **Procedural** | 도구별 실행 성공/실패 이력 | Executor가 도구 결과를 더 잘 해석하도록 가이드 |

**Memory Rewriting**: 동일 task 재실행 시, 기존보다 score가 0.1 이상 높을 때만 교체. 더 나쁜 결과는 저장하지 않음.

---

## 📚 References

- [Memento 2 Paper](https://arxiv.org/abs/2512.22716) - Learning by Stateful Reflective Memory
- [MCP Protocol](https://modelcontextprotocol.io) - Model Context Protocol
- [Chronos Forecasting](https://github.com/amazon-science/chronos-forecasting) - 시계열 예측
- [yfinance](https://github.com/ranaroussi/yfinance) - 주식 데이터
- [FinanceDataReader](https://github.com/FinanceData/FinanceDataReader) - 한국 주식 가격
- [PyKRX](https://github.com/sharebook-kr/pykrx) - 한국 주식 재무지표

---

⚠️ **Disclaimer**: 본 시스템의 분석은 참고용이며, 투자 결정은 본인 책임입니다.
