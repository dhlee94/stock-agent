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
    """Load FinBERT model + tokenizer, converting .bin → safetensors on first use."""
    from safetensors.torch import save_file

    cache_dir = Path.home() / ".cache" / "finbert_safetensors"
    safe_dir = cache_dir / model_id.replace("/", "_")
    safe_path = safe_dir / "model.safetensors"

    if not safe_path.exists():
        print(f"   🔄 Converting {model_id} .bin → safetensors (one-time)...")
        safe_dir.mkdir(parents=True, exist_ok=True)

        from transformers import modeling_utils as _mu
        _orig = _mu.check_torch_load_is_safe
        _mu.check_torch_load_is_safe = lambda: None
        try:
            model = AutoModelForSequenceClassification.from_pretrained(model_id)
            tokenizer = AutoTokenizer.from_pretrained(model_id)
        finally:
            _mu.check_torch_load_is_safe = _orig

        save_file(model.state_dict(), str(safe_path))
        model.config.save_pretrained(str(safe_dir))
        tokenizer.save_pretrained(str(safe_dir))
        print(f"   ✅ Saved to {safe_dir}")
        return model.to(device), tokenizer

    print(f"   ✅ Loading {model_id} from safetensors cache")
    model = AutoModelForSequenceClassification.from_pretrained(
        str(safe_dir), use_safetensors=True
    )
    tokenizer = AutoTokenizer.from_pretrained(str(safe_dir))
    return model.to(device), tokenizer

def _resolve_torch_device() -> "torch.device":
    setting = os.environ.get("TORCH_DEVICE", "auto").lower()
    if setting == "auto":
        if torch.cuda.is_available():
            return torch.device("cuda")
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")
    return torch.device(setting)


SENTIMENT_MODEL_BY_MARKET = {
    "US": "ProsusAI/finbert",
    "KR": "snunlp/KR-FinBert-SC",
}


class StockBrain:
    """
    Lightweight wrapper for news sentiment classification.
    (English ProsusAI/finbert for US, Korean snunlp/KR-FinBert-SC for KR)
    """

    def __init__(self, ticker_symbol, ticker_name, market_type):
        self.device = _resolve_torch_device()
        print(f"🧠 {ticker_name} ({ticker_symbol}) brain init... (Device: {self.device})")

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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stock news sentiment (FinBERT)")
    parser.add_argument("--ticker", type=str, default="005930.KS")
    parser.add_argument("--name", type=str, default="Samsung Electronics")
    parser.add_argument("--market", type=str, default="KR", choices=["KR", "US"])
    args = parser.parse_args()

    brain = StockBrain(args.ticker, args.name, args.market)
    news = brain.loader.get_news()

    sentiment = brain.get_news_sentiment(news)

    print("\n--- News sentiment (FinBERT) ---")
    print(sentiment)
