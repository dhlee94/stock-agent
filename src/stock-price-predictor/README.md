# 📈 Multimodal Stock Price Predictor

> **딥러닝 아키텍처와 통계적 검증 모델을 결합한 지능형 주가 분석 시스템** > 뉴스 감성 분석(NLP)과 시계열 차트 데이터(Time-series)를 **Cross-Attention** 메커니즘으로 결합하여 최적의 매수/매도 신호를 생성합니다.

---

### ✨ Key Features

* **Multimodal Fusion**: `FinBERT`의 뉴스 감성 벡터와 `Chronos-T5`의 시계열 특징을 결합한 하이브리드 예측 엔진.
* **Volatility-Aware Loss**: 주가 변동성이 큰 구간에서 모델이 더 정교하게 학습하도록 설계된 커스텀 손실 함수.
* **Statistical Gatekeeper**: **Wilson Score Method**를 활용하여 데이터가 부족하거나 최근 승률이 낮을 경우 신호를 차단하는 안전장치.
* **Explainable AI (XAI)**: **Attention Map** 시각화를 통해 모델이 어떤 뉴스 키워드에 집중했는지 분석 가능.
* **Real-time Analysis**: `yfinance` 및 `GoogleNews API`를 통한 실시간 데이터 파이프라인 구축.

---

### 📂 Project Structure

```plaintext
stock-price-predictor/
├── src/
│   ├── data/             # 데이터 로딩 및 전처리 (yfinance, News API)
│   ├── models/           # Fusion 레이어 및 VolatilityLoss 정의
│   ├── utils/            # Wilson Score 등 통계 분석 도구
│   └── visualization/    # Attention Map 시각화 도구
├── main.py               # 통합 분석 실행 스크립트
├── trainer.py            # 모델 파인튜닝 스크립트
└── requirements.txt      # 의존성 패키지 목록
```
---

## 🚀 Quick Start

### 1. Requirements
프로젝트 실행을 위해 필요한 라이브러리들을 먼저 설치해 주세요.

```Bash
pip install -r requirements.txt
```
### 2. Run Analysis
기본적으로 Microsoft(MSFT) 또는 **삼성전자(005930.KS)**를 대상으로 10분 간격의 실시간 분석을 수행합니다.

```Bash
python main.py
```
### 3. Model Training
수집된 데이터를 바탕으로 MultimodalFusion 레이어를 최적화하여 모델의 예측력을 개선합니다.

```bash
python trainer.py
```
