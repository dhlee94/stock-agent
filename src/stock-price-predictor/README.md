# Stock Price Predictor (Legacy / News Sentiment focus)

본 모듈은 주가 분석 에이전트의 뉴스 감성 분석 엔진을 담당합니다.

## Key Features

* **Real-time News Sentiment**: `FinBERT`을 활용하여 최신 뉴스 헤드라인의 감성(긍정/부정)을 분류합니다.
* **Factual Data Loading**: `yfinance`를 통해 주가 및 거래량 데이터를 안정적으로 수집합니다.

## Project Structure

```plaintext
stock-price-predictor/
├── predictor_src/
│   ├── data/             # 데이터 로딩 및 전처리
│   └── utils/            # 통계 분석 도구
├── main.py               # 통합 분석 실행 스크립트 (FinBERT 중심)
└── README.md             # 본 문서
```

## Quick Start

### 1. Requirements
```Bash
pip install -r requirements.txt
```

### 2. Run Analysis
기본적으로 뉴스 감성 분석을 수행합니다.
```Bash
python main.py --ticker 005930.KS --name 삼성전자 --market KR
```
