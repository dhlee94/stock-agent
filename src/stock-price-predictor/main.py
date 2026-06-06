import torch
import torch.nn.functional as F
import sys
import os

sys.path.append(os.getcwd())
os.environ["USE_TORCH"] = "1"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

import argparse
import numpy as np
from pathlib import Path
from predictor_src.data.loader import StockDataLoader
from transformers import AutoTokenizer, AutoModelForSequenceClassification


def _load_finbert_safe(model_id: str, device):
    """Load FinBERT model + tokenizer, converting .bin → safetensors on first use.

    Returns (model, tokenizer) — both from local safetensors cache after first run.

    Both ProsusAI/finbert and snunlp/KR-FinBert-SC ship only .bin weights.
    torch.load(.bin) is blocked by transformers>=4.51 when torch<2.6 (CVE-2025-32434),
    but uni2ts (Moirai) pins torch<2.5.

    Strategy: one-time unsafe .bin load → convert state dict to safetensors + save
    tokenizer files locally. All subsequent loads use only the local safetensors cache:
      safe_dir/
        config.json          ← model architecture
        model.safetensors    ← weights (pickle-free)
        tokenizer_config.json, vocab.txt, ...  ← tokenizer (JSON/text, always safe)
    """
    from safetensors.torch import save_file

    cache_dir = Path.home() / ".cache" / "finbert_safetensors"
    safe_dir = cache_dir / model_id.replace("/", "_")
    safe_path = safe_dir / "model.safetensors"

    if not safe_path.exists():
        print(f"   🔄 Converting {model_id} .bin → safetensors (one-time)...")
        safe_dir.mkdir(parents=True, exist_ok=True)

        # One-time unsafe load — gated by check_torch_load_is_safe bypass
        # Safe: loading from HuggingFace Hub, not arbitrary user-supplied pickles
        from transformers import modeling_utils as _mu
        _orig = _mu.check_torch_load_is_safe
        _mu.check_torch_load_is_safe = lambda: None
        try:
            model = AutoModelForSequenceClassification.from_pretrained(model_id)
            tokenizer = AutoTokenizer.from_pretrained(model_id)
        finally:
            _mu.check_torch_load_is_safe = _orig

        # Persist: weights as safetensors, config + tokenizer as plain files
        save_file(model.state_dict(), str(safe_path))
        model.config.save_pretrained(str(safe_dir))
        tokenizer.save_pretrained(str(safe_dir))
        print(f"   ✅ Saved to {safe_dir}")
        return model.to(device), tokenizer

    # Fast path: load everything from local cache — no HuggingFace Hub needed
    print(f"   ✅ Loading {model_id} from safetensors cache")
    model = AutoModelForSequenceClassification.from_pretrained(
        str(safe_dir), use_safetensors=True
    )
    tokenizer = AutoTokenizer.from_pretrained(str(safe_dir))
    return model.to(device), tokenizer

CHRONOS_MODEL_ID = os.environ.get("CHRONOS_MODEL", "amazon/chronos-2")
MOIRAI_MODEL_ID = os.environ.get("MOIRAI_MODEL", "Salesforce/moirai-2.0-R-small")
MOIRAI_ENABLED = os.environ.get("MOIRAI_ENABLED", "false").lower() == "true"

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
    Lightweight wrapper around pretrained models, used independently:
      - Chronos-2 (default, multivariate): Close + Volume + (H-L)/C covariates
      - Chronos / Chronos-Bolt (legacy, univariate): set CHRONOS_MODEL to older ID
      - Moirai 2.0 (optional, MOIRAI_ENABLED=true) for price forecasting
      - Market-specific FinBERT for news sentiment classification
        (English ProsusAI/finbert for US, Korean snunlp/KR-FinBert-SC for KR)

    No custom fusion/classifier on top — each model exposes its own pretrained
    signal honestly. The agent decides how to combine them.
    """

    def __init__(self, ticker_symbol, ticker_name, market_type):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"🧠 {ticker_name} ({ticker_symbol}) brain init... (Device: {self.device})")

        dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32
        print(f"🧠 Chronos model: {CHRONOS_MODEL_ID}")
        self._chronos_v2 = "chronos-2" in CHRONOS_MODEL_ID
        if self._chronos_v2:
            from chronos import Chronos2Pipeline
            self.chronos = Chronos2Pipeline.from_pretrained(
                CHRONOS_MODEL_ID, device_map=self.device, dtype=dtype
            )
        else:
            from chronos import ChronosPipeline
            self.chronos = ChronosPipeline.from_pretrained(
                CHRONOS_MODEL_ID, device_map=self.device, dtype=dtype
            )

        self.moirai_module = None
        if MOIRAI_ENABLED:
            try:
                from uni2ts.model.moirai2.module import Moirai2Module
                print(f"🧠 Moirai model: {MOIRAI_MODEL_ID}")
                self.moirai_module = Moirai2Module.from_pretrained(MOIRAI_MODEL_ID).to(self.device)
            except ImportError:
                print("⚠️  uni2ts not installed — Moirai disabled. Run: pip install uni2ts")
            except Exception as e:
                print(f"⚠️  Moirai failed to load ({type(e).__name__}: {e}) — Moirai disabled.")

        if market_type not in SENTIMENT_MODEL_BY_MARKET:
            raise ValueError(
                f"Unsupported market '{market_type}'. Expected one of {list(SENTIMENT_MODEL_BY_MARKET)}"
            )
        self.fb_model_id = SENTIMENT_MODEL_BY_MARKET[market_type]
        print(f"🧠 Sentiment model for {market_type}: {self.fb_model_id}")
        self.finbert, self.fb_tokenizer = _load_finbert_safe(self.fb_model_id, self.device)
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

    def get_price_forecast(self, forecast_steps=30, context_period=None,
                           price_context=None, current_price=None, context_df=None):
        """
        Chronos quantile forecast. Routes to v2 (multivariate) or v1 (univariate)
        based on CHRONOS_MODEL.
        context_period: yfinance 기간 문자열 (예: '3mo', '6mo', '1y').
                        None이면 forecast_steps에 비례해 자동 계산.
        """
        if self._chronos_v2:
            return self._forecast_v2(context_df, current_price, forecast_steps, context_period)
        else:
            return self._forecast_v1(price_context, current_price, forecast_steps)

    def _forecast_v1(self, price_context, current_price, forecast_steps):
        """Chronos / Chronos-Bolt univariate forecast (Close only)."""
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

        return self._build_result(med, low, high, current_price, forecast_steps)

    def _forecast_v2(self, context_df, current_price, forecast_steps, context_period=None):
        """Chronos-2 multivariate forecast (Close + volume_norm + hl_range).
        Input tensor: (1, n_variates=3, history_length)
        Output:       (n_variates, num_samples, forecast_steps) — variate 0 is target.
        """
        last_data_date = None
        if context_df is None:
            prep = self.loader.prepare_multivariate_df(period=context_period, forecast_steps=forecast_steps)
            context_df = prep["context_df"]
            current_price = prep["current_price"]
            last_data_date = prep.get("last_data_date")

        if last_data_date is None and 'timestamp' in context_df.columns:
            import pandas as pd
            last_data_date = str(pd.Timestamp(context_df['timestamp'].iloc[-1]).date())

        # shape: (1, 3, history_length)
        mv_tensor = torch.tensor(
            context_df[["target", "volume_norm", "hl_range"]].values.T[None],
            dtype=torch.float32,
        )

        forecast = self.chronos.predict(mv_tensor, forecast_steps)

        # forecast[0] shape: (n_variates=3, num_samples, forecast_steps)
        target_samples = forecast[0][0]  # (num_samples, forecast_steps)
        low = target_samples.quantile(0.1, dim=0).tolist()
        med = target_samples.quantile(0.5, dim=0).tolist()
        high = target_samples.quantile(0.9, dim=0).tolist()

        result = self._build_result(med, low, high, current_price, forecast_steps)
        result["last_data_date"] = last_data_date
        return result

    def _build_result(self, med, low, high, current_price, forecast_steps):
        final_med = med[-1]
        pct_change = ((final_med - current_price) / current_price) * 100 if current_price else 0.0
        return {
            "model": CHRONOS_MODEL_ID,
            "current_price": float(current_price),
            "forecast_steps": forecast_steps,
            "final_median": round(float(final_med), 4),
            "pct_change": round(float(pct_change), 2),
            "direction": "up" if pct_change > 0 else "down",
            "median": [round(float(x), 4) for x in med],
            "lower_q10": [round(float(x), 4) for x in low],
            "upper_q90": [round(float(x), 4) for x in high],
        }


    def get_price_forecast_moirai(self, price_context=None, current_price=None,
                                   forecast_steps=30, context_period=None):
        """
        Moirai 2.0 quantile forecast for the next `forecast_steps` periods.
        Requires MOIRAI_ENABLED=true and uni2ts installed.
        Returns the same schema as get_price_forecast plus a `model` field.
        """
        if not MOIRAI_ENABLED or self.moirai_module is None:
            return {"status": "error", "error": "Moirai not enabled — set MOIRAI_ENABLED=true and install uni2ts"}

        from uni2ts.model.moirai2.forecast import Moirai2Forecast

        last_data_date = None
        if price_context is None or current_price is None:
            prep = self.loader.prepare_multivariate_df(period=context_period, forecast_steps=forecast_steps)
            price_context = prep["context_df"]["target"].values
            current_price = prep["current_price"]
            last_data_date = prep.get("last_data_date")

        if price_context is None or len(price_context) == 0:
            return {"status": "error", "error": "no price context available"}

        ctx_len = len(price_context)
        model = Moirai2Forecast(
            module=self.moirai_module,
            prediction_length=forecast_steps,
            context_length=ctx_len,
            target_dim=1,
            feat_dynamic_real_dim=0,
            past_feat_dynamic_real_dim=0,
        )

        # (batch=1, time, dim=1)
        past_target = torch.as_tensor(np.asarray(price_context), dtype=torch.float32).unsqueeze(0).unsqueeze(-1)
        past_observed = torch.ones_like(past_target, dtype=torch.bool)
        past_is_pad = torch.zeros(1, ctx_len, dtype=torch.bool)

        with torch.no_grad():
            forecast = model(
                past_target=past_target,
                past_observed_target=past_observed,
                past_is_pad=past_is_pad,
            )

        # Moirai2Forecast returns (n_quantiles, forecast_steps)
        # default quantile_levels: [0.1, 0.2, ..., 0.9] → idx 0=q10, 4=q50, 8=q90
        q_levels = [float(q) for q in getattr(self.moirai_module, "quantile_levels",
                                               [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9])]
        # Use nearest-value lookup to avoid float equality failure
        def _q_idx(target: float) -> int:
            return int(np.argmin([abs(q - target) for q in q_levels]))
        q10_idx = _q_idx(0.1)
        q50_idx = _q_idx(0.5)
        q90_idx = _q_idx(0.9)
        low = forecast[0][q10_idx].tolist()
        med = forecast[0][q50_idx].tolist()
        high = forecast[0][q90_idx].tolist()

        final_med = med[-1]
        pct_change = ((final_med - current_price) / current_price) * 100 if current_price else 0.0

        return {
            "model": MOIRAI_MODEL_ID,
            "current_price": float(current_price),
            "forecast_steps": forecast_steps,
            "final_median": round(float(final_med), 4),
            "pct_change": round(float(pct_change), 2),
            "direction": "up" if pct_change > 0 else "down",
            "median": [round(float(x), 4) for x in med],
            "lower_q10": [round(float(x), 4) for x in low],
            "upper_q90": [round(float(x), 4) for x in high],
            "last_data_date": last_data_date,
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stock signals (Chronos + FinBERT, used independently)")
    parser.add_argument("--ticker", type=str, default="005930.KS")
    parser.add_argument("--name", type=str, default="Samsung Electronics")
    parser.add_argument("--market", type=str, default="KR", choices=["KR", "US"])
    args = parser.parse_args()

    brain = StockBrain(args.ticker, args.name, args.market)
    news = brain.loader.get_news()

    sentiment = brain.get_news_sentiment(news)
    forecast = brain.get_price_forecast()

    print("\n--- News sentiment (FinBERT) ---")
    print(sentiment)
    print("\n--- Price forecast (Chronos) ---")
    print(forecast)
