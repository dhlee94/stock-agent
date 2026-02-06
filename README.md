# 🤖 Stock Expert AI Agent

> **AI 기반 주식 전문가 에이전트**  
> Chronos + FinBERT 멀티모달 분석, 기술적/기본적 분석, 실시간 데이터

---

## ✨ Features

- 🧠 **Dual-LLM Architecture**: Memento 논문 기반 Planner(계획) + Executor(실행) 분리 구조
- 💬 **Interactive Chat**: 자연어 에이전트 채팅 인터페이스
- 📊 **Technical Analysis**: RSI, MACD, Bollinger Bands, Moving Averages
- 📈 **Fundamental Analysis**: PER, PBR, ROE, EPS, 재무제표
- 🤖 **AI Prediction**: Chronos 시계열 + FinBERT 감성 분석
- 📰 **Real-time News**: 종목별 뉴스 및 시장 동향
- 📱 **Web Dashboard**: 모바일/PC 접속 가능한 웹 UI

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
echo "GEMINI_API_KEY=your-key" > .env
```

### 3. Run (택 1)

#### 📱 웹 대시보드 (추천)
```bash
source venv/bin/activate
python src/web/app.py
```
**접속**: http://localhost:8000

**핸드폰 접속**: 같은 WiFi에서 `http://<맥IP주소>:8000`

#### 💻 CLI Agent
```bash
source venv/bin/activate
python main.py "삼성전자 분석해줘"
python main.py "NVDA 앞으로 전망 어때?"
```

---

## 📂 Project Structure

```
agent/
├── main.py                   # CLI 진입점
├── requirements.txt
├── .env                      # API 키 (직접 생성)
└── src/
    ├── agent_client.py       # Stock Expert Agent
    ├── mcp_server.py         # MCP Tool Server
    ├── memory_store.py       # Memory Store
    ├── web/                  # 📱 웹 대시보드
    │   ├── app.py            # FastAPI 서버
    │   ├── templates/        # HTML
    │   └── static/           # CSS
    └── tools/
        ├── stock/            # 📈 Stock Tools
        │   ├── price.py      # 실시간 주가
        │   ├── chart.py      # 차트 데이터
        │   ├── financials.py # 재무제표
        │   ├── news.py       # 뉴스
        │   ├── technical.py  # 기술적 분석
        │   ├── compare.py    # 종목 비교
        │   ├── sector.py     # 섹터 분석
        │   └── predictor.py  # AI 예측
        └── ...               # 유틸리티
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
| `LLM_PROVIDER` | `gemini` (기본), `openai`, 또는 `groq` |
| `GEMINI_API_KEY` | Gemini API 키 (무료) |
| `OPENAI_API_KEY` | OpenAI API 키 (유료) |
| `GROQ_API_KEY` | Groq API 키 (무료, Llama 3.3 70B) |

---

## 📚 References

- [Memento Paper](https://arxiv.org/abs/2401.08017)
- [MCP Protocol](https://modelcontextprotocol.io)
- [Chronos Forecasting](https://github.com/amazon-science/chronos-forecasting)
- [FinBERT](https://huggingface.co/ProsusAI/finbert)

---

⚠️ **Disclaimer**: 본 시스템의 분석은 참고용이며, 투자 결정은 본인 책임입니다.
