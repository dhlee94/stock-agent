# 🤖 Stock Expert AI Agent

> **AI 기반 주식 전문가 에이전트**  
> Chronos + FinBERT 멀티모달 분석, 기술적/기본적 분석, 실시간 데이터

---

## ✨ Features

- 📊 **Technical Analysis**: RSI, MACD, Bollinger Bands, Moving Averages
- 📈 **Fundamental Analysis**: PER, PBR, ROE, EPS, 재무제표
- 🤖 **AI Prediction**: Chronos 시계열 + FinBERT 감성 분석
- 📰 **Real-time News**: 종목별 뉴스 및 시장 동향
- ⚖️ **Stock Comparison**: 다중 종목 비교 분석
- 🏭 **Sector Analysis**: 업종별 분석 (반도체, 2차전지, 바이오 등)

---

## 📂 Project Structure

```
agent/
├── main.py
├── requirements.txt
├── .env.example
└── src/
    ├── agent_client.py          # Stock Expert Agent
    ├── mcp_server.py             # MCP Tool Server
    ├── memory_store.py           # Memory Store
    └── tools/
        ├── stock/                # 📈 Stock Analysis Tools
        │   ├── price.py          # 실시간 주가
        │   ├── chart.py          # 차트 데이터
        │   ├── financials.py     # 재무제표
        │   ├── news.py           # 뉴스
        │   ├── technical.py      # 기술적 분석
        │   ├── compare.py        # 종목 비교
        │   ├── sector.py         # 섹터 분석
        │   └── predictor.py      # AI 예측
        ├── search.py, crawl.py   # 유틸리티
        └── ...
```

---

## 🚀 Quick Start

```bash
# Setup
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Configure API Key
echo "GEMINI_API_KEY=your-key" > .env

# Run Stock Expert
python main.py "삼성전자 분석해줘"
python main.py "NVDA 기술적 분석"
python main.py "반도체 섹터 분석"
```

---

## 📈 Available Stock Tools

| Tool | Description |
|------|-------------|
| `stock_price` | 실시간 주가, 등락률, 거래량 |
| `stock_chart` | OHLCV 차트 데이터 |
| `stock_financials` | PER, PBR, ROE, 배당 등 |
| `stock_news` | 종목/시장 뉴스 |
| `stock_technical` | RSI, MACD, 볼린저밴드, MA |
| `stock_compare` | 다중 종목 비교 |
| `stock_sector` | 섹터별 분석 |
| `stock_ai_predict` | AI 예측 (Chronos + FinBERT) |

---

## 🔧 Environment Variables

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Gemini API 키 |
| `OPENAI_API_KEY` | OpenAI API 키 (선택) |

---

## 📚 References

- [Memento Paper](https://arxiv.org/abs/2401.08017)
- [MCP Protocol](https://modelcontextprotocol.io)
- [Chronos Forecasting](https://github.com/amazon-science/chronos-forecasting)
- [FinBERT](https://huggingface.co/ProsusAI/finbert)

---

⚠️ **Disclaimer**: 본 시스템의 분석은 참고용이며, 투자 결정은 본인 책임입니다.
