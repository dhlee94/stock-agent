import torch
import torch.nn.functional as F
import sys
import os
import base64

# Monkey patch for libraries using deprecated base64.decodestring
if not hasattr(base64, "decodestring"):
    base64.decodestring = base64.decodebytes
sys.path.append(os.getcwd())
os.environ["USE_TORCH"] = "1"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

import argparse
import numpy as np
from predictor_src.data.loader import StockDataLoader
from chronos import ChronosPipeline
from transformers import AutoTokenizer, AutoModelForSequenceClassification


# Market → financial-sentiment model. Each model is used in its native
# language; no translation step.
#   US: ProsusAI/finbert    — English, 3-class (positive/neutral/negative)
#   KR: snunlp/KR-FinBert-SC — Korean,  2-class (positive/negative)
SENTIMENT_MODEL_BY_MARKET = {
    "US": "ProsusAI/finbert",
    "KR": "snunlp/KR-FinBert-SC",
}


class StockBrain:
    """
    Lightweight wrapper around two pretrained models, used independently:
      - Chronos (amazon/chronos-t5-small) for price forecasting
      - Market-specific FinBERT for news sentiment classification
        (English ProsusAI/finbert for US, Korean snunlp/KR-FinBert-SC for KR)

    No custom fusion/classifier on top — each model exposes its own pretrained
    signal honestly. The agent decides how to combine them.
    """

    def __init__(self, ticker_symbol, ticker_name, market_type):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"🧠 {ticker_name} ({ticker_symbol}) brain init... (Device: {self.device})")

        self.chronos = ChronosPipeline.from_pretrained(
            "amazon/chronos-t5-small",
            device_map=self.device,
            dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
        )

        if market_type not in SENTIMENT_MODEL_BY_MARKET:
            raise ValueError(
                f"Unsupported market '{market_type}'. Expected one of {list(SENTIMENT_MODEL_BY_MARKET)}"
            )
        self.fb_model_id = SENTIMENT_MODEL_BY_MARKET[market_type]
        print(f"🧠 Sentiment model for {market_type}: {self.fb_model_id}")
        self.fb_tokenizer = AutoTokenizer.from_pretrained(self.fb_model_id)
        self.finbert = AutoModelForSequenceClassification.from_pretrained(self.fb_model_id).to(self.device)
        self.finbert.eval()
        self.fb_id2label = {int(k): v.lower() for k, v in self.finbert.config.id2label.items()}
        self.fb_supported_labels = sorted(set(self.fb_id2label.values()))

        self.loader = StockDataLoader(ticker_symbol, ticker_name, market_type)
        self.market_type = market_type

    def get_news_sentiment(self, news_list=None):
        """
        Per-headline sentiment + aggregate distribution, using the
        market-appropriate model (English FinBERT for US, KR-FinBert for KR).

        Returns:
            {
              "model_id": str,                  # which model produced this
              "supported_labels": [str],        # what classes the model emits
                                                #   US: [negative, neutral, positive]
                                                #   KR: [negative, positive]
              "distribution": {label: prob},    # mean probability across headlines
              "dominant": label,
              "headlines": [{"title", "label", "score"}],
              "count": int,
            }
        """
        if news_list is None:
            news_list = self.loader.get_news()

        base = {
            "model_id": self.fb_model_id,
            "supported_labels": self.fb_supported_labels,
        }

        if not news_list:
            return {
                **base,
                "distribution": {label: 0.0 for label in self.fb_supported_labels},
                "dominant": None,
                "headlines": [],
                "count": 0,
            }

        inputs = self.fb_tokenizer(
            news_list, return_tensors="pt", padding=True, truncation=True, max_length=512
        ).to(self.device)

        with torch.no_grad():
            logits = self.finbert(**inputs).logits
            probs = F.softmax(logits, dim=-1).cpu()

        mean_probs = probs.mean(dim=0).tolist()
        distribution = {self.fb_id2label[i]: round(float(p), 4) for i, p in enumerate(mean_probs)}
        dominant = max(distribution, key=distribution.get)

        headlines = []
        for title, row in zip(news_list, probs):
            row_dict = {self.fb_id2label[i]: round(float(p), 4) for i, p in enumerate(row.tolist())}
            best_label = max(row_dict, key=row_dict.get)
            headlines.append({"title": title, "label": best_label, "score": row_dict[best_label]})

        return {
            **base,
            "distribution": distribution,
            "dominant": dominant,
            "headlines": headlines,
            "count": len(news_list),
        }

    def get_price_forecast(self, price_context=None, current_price=None, forecast_steps=30):
        """
        Chronos quantile forecast for the next `forecast_steps` periods.
        Returns:
            {
              "current_price", "forecast_steps", "final_median",
              "pct_change", "direction",
              "median", "lower_q10", "upper_q90",  # trajectories
            }
        """
        if price_context is None or current_price is None:
            prep = self.loader.prepare_all()
            price_context = prep["price_context"]
            current_price = prep["current_price"]

        if price_context is None or len(price_context) == 0:
            return {"status": "error", "error": "no price context available"}

        context_tensor = torch.tensor(np.asarray(price_context), dtype=torch.float32)
        forecast = self.chronos.predict(context_tensor, forecast_steps)

        low = forecast[0].quantile(0.1, dim=0).tolist()
        med = forecast[0].quantile(0.5, dim=0).tolist()
        high = forecast[0].quantile(0.9, dim=0).tolist()

        final_med = med[-1]
        pct_change = ((final_med - current_price) / current_price) * 100 if current_price else 0.0

        return {
            "current_price": float(current_price),
            "forecast_steps": forecast_steps,
            "final_median": round(float(final_med), 4),
            "pct_change": round(float(pct_change), 2),
            "direction": "up" if pct_change > 0 else "down",
            "median": [round(float(x), 4) for x in med],
            "lower_q10": [round(float(x), 4) for x in low],
            "upper_q90": [round(float(x), 4) for x in high],
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stock signals (Chronos + FinBERT, used independently)")
    parser.add_argument("--ticker", type=str, default="005930.KS")
    parser.add_argument("--name", type=str, default="Samsung Electronics")
    parser.add_argument("--market", type=str, default="KR", choices=["KR", "US"])
    args = parser.parse_args()

    brain = StockBrain(args.ticker, args.name, args.market)
    prep = brain.loader.prepare_all()

    sentiment = brain.get_news_sentiment(prep["news"])
    forecast = brain.get_price_forecast(prep["price_context"], prep["current_price"])

    print("\n--- News sentiment (FinBERT) ---")
    print(sentiment)
    print("\n--- Price forecast (Chronos) ---")
    print(forecast)
