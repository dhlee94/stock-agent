# 🤖 Stock Expert AI Agent

> **AI 기반 주식 전문가 에이전트**  
> Memento 멀티모달 분석 + 리스크 관리 + 다국어 지원

---

## ✨ Features

- 🧠 **Memento Architecture**: [논문](https://arxiv.org/abs/2401.08017) 기반 Planner/Executor/Reflector 구조
- 📊 **Technical Analysis**: RSI, MACD, Bollinger Bands, Moving Averages
- 📈 **Fundamental Analysis**: PER, PBR, ROE, EPS, 재무제표
- 🤖 **AI Prediction**: Chronos 시계열 예측
- 📰 **Multi-language News**: 한국/미국 주식 자동 감지, 영어→한글 분석
- 🎯 **Risk Management**: Target Price, Stop-loss, Risk/Reward 자동 계산
- 💾 **Memory System**: DriverMemory (주가 변동 원인), ProceduralMemory (성공 패턴)
- 🔍 **Self-Reflection**: 논리적 일관성 검증 및 자동 수정
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

#### 📱 웹 대시보드 (추천)
```bash
source venv/bin/activate
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
┌─────────────────────────▼───────────────────────────────────┐
│                   🧠 PLANNER (LLM)                          │
│  - 사용자 요청 분석                                          │
│  - DriverMemory 조회 (과거 주가 변동 원인)                    │
│  - 실행 계획 수립                                            │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                   ⚡ EXECUTOR                               │
│  MCP Tools: price, technical, news, risk, predict...       │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                   🔍 REFLECTOR (Self-Check)                 │
│  - 논리적 일관성 검증 (RSI < 30 인데 SELL?)                   │
│  - 누락된 분석 체크                                          │
│  - 필요시 재분석                                             │
└─────────────────────────┴───────────────────────────────────┘
```

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
    ├── memory_store.py        # Embedding 기반 메모리
    ├── driver_memory.py       # 📈 Driver Memory (주가 변동 원인)
    ├── risk_manager.py        # 🎯 Risk Management
    ├── web/                   # 📱 웹 대시보드
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
| `analyze_peers` | 📊 뉴스 Entity Mining + STL Trend 유사도 분석 |

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
| `GEMINI_API_KEY` | Yes* | Gemini API 키 (무료) |
| `OPENAI_API_KEY` | No | OpenAI API 키 (유료) |

*최소 하나의 LLM API 키 필요

---

## 📚 References

- [Memento Paper](https://arxiv.org/abs/2401.08017) - Self-Refinement 에이전트 아키텍처
- [MCP Protocol](https://modelcontextprotocol.io) - Model Context Protocol
- [Chronos Forecasting](https://github.com/amazon-science/chronos-forecasting) - 시계열 예측
- [yfinance](https://github.com/ranaroussi/yfinance) - 주식 데이터

---

⚠️ **Disclaimer**: 본 시스템의 분석은 참고용이며, 투자 결정은 본인 책임입니다.
