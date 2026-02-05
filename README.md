# 🤖 Memento AI Agent

> **Memento Paper 기반의 MCP Agent 시스템**  
> 과거 성공 경험을 Vector DB로 저장하고, 유사 작업 시 참조하여 더 나은 계획을 세웁니다.

---

## ✨ Features

- **Memory-Augmented Planning**: 과거 성공 trajectory를 벡터 검색으로 참조
- **MCP Protocol**: Tool 호출 표준화 (Search, Crawl, Code, Math, Stock 등)
- **Multi-LLM Support**: Gemini (무료) 또는 OpenAI 선택 가능
- **Stock Analysis**: Chronos + FinBERT 기반 주가 예측 도구 통합

---

## 📂 Project Structure

```
Agents/
├── agent_client.py      # Main Agent (LLM + Memory + MCP)
├── mcp_server.py        # MCP Tool Server
├── memory_store.py      # Vector-based Memory Store
├── stock_tool.py        # Stock Analysis Wrapper
├── stock-price-predictor/  # Submodule: AI Stock Predictor
├── requirements.txt
├── .env                 # API Keys (gitignored)
└── run_demo.sh          # Quick Start Script
```

---

## 🚀 Quick Start

### 1. Setup
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure API Key
```bash
# .env 파일 생성
echo "GEMINI_API_KEY=your-api-key-here" > .env
```

### 3. Run Agent
```bash
python agent_client.py "AI 뉴스 찾아줘"
python agent_client.py "삼성전자 주가 분석해줘"
python agent_client.py "NVDA 주가 예측해줘"
```

---

## 🛠️ Available Tools

| Tool | Description |
|------|-------------|
| `search_web` | 웹 검색 |
| `crawl_url` | URL 크롤링 (Playwright) |
| `search_video` | 동영상 검색 |
| `process_image` | 이미지 생성/분석 |
| `execute_python` | Python 코드 실행 |
| `calculate_math` | 수학 계산 |
| `read_document` | 문서 읽기 |
| `save_feedback` | 메모리에 저장 |
| `analyze_stock` | 📈 주가 분석 (AI) |

---

## 📈 Stock Analysis

`analyze_stock` 도구는 다음을 반환합니다:
- **Current Price**: 현재 주가
- **AI Score**: 0~1 (높을수록 상승 가능성)
- **Sentiment**: Bullish / Bearish
- **Recommendation**: STRONG BUY / BUY / HOLD / SELL / STRONG SELL
- **Top News**: 최신 관련 뉴스

---

## 🔧 Environment Variables

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Gemini API 키 (기본) |
| `OPENAI_API_KEY` | OpenAI API 키 (선택) |
| `LLM_PROVIDER` | `gemini` 또는 `openai` |

---

## 📚 References

- [Memento Paper](https://arxiv.org/abs/2401.08017) - Fine-tuning LLM Agents without Fine-tuning LLMs
- [MCP Protocol](https://modelcontextprotocol.io) - Model Context Protocol
- [Chronos](https://github.com/amazon-science/chronos-forecasting) - Time Series Forecasting
- [FinBERT](https://huggingface.co/ProsusAI/finbert) - Financial Sentiment Analysis
