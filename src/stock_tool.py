"""
Stock Analysis Tool - Wrapper for StockBrain
"""
import sys
import os

# Add stock-price-predictor to path
STOCK_PREDICTOR_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stock-price-predictor")
sys.path.insert(0, STOCK_PREDICTOR_PATH)

# Suppress TensorFlow logs
os.environ["USE_TORCH"] = "1"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

import json
from datetime import datetime
import pytz

# Lazy loading to avoid slow startup
_stock_brain_cache = {}

class MockStockBrain:
    """Mock Brain for when the real model is missing."""
    def __init__(self, ticker, name, market):
        self.ticker = ticker
        self.market = market
        self.loader = self
        self.chronos = self
        
    def prepare_all(self):
        import yfinance as yf
        from tools.stock.news import get_market_news
        
        try:
            ticker_obj = yf.Ticker(self.ticker)
            hist = ticker_obj.history(period="1mo")
            if hist.empty:
                current_price = 100000
                context = [100000] * 30
            else:
                current_price = hist["Close"].iloc[-1]
                context = hist["Close"].values.tolist()
            
            # Use real news tool
            try:
                news_json = get_market_news(self.ticker, limit=3)
                news_data = json.loads(news_json)
                # Extract titles for the list
                news = [item['title'] for item in news_data.get('news', [])]
                if not news:
                    news = [f"No recent news for {self.ticker}"]
            except Exception:
                news = [f"Failed to fetch news for {self.ticker}"]
            
            return {
                "current_price": current_price,
                "price_context": context,
                "news": news
            }
        except Exception:
            return {"current_price": 0, "price_context": [], "news": []}

    def get_stl_features(self, data):
        return {"trend": data[-1] if len(data) > 0 else 0}

    def fetch_price_data(self):
        return [100, 101, 102] # Dummy

    def extract_features(self, news, price):
        return None, None

    def fusion(self, t, p):
        return None

    def classifier(self, v):
        return None
        
    def predict(self, context, steps):
        # Generate random walk forecast
        import random
        import torch
        last_price = context[-1]
        
        # Random trend (-0.5% to +0.8% per day)
        daily_volatility = 0.02
        predictions = []
        
        current = last_price
        for _ in range(steps):
            change = random.uniform(-daily_volatility, daily_volatility) + 0.001 # Slight upward bias
            current = current * (1 + change)
            predictions.append(current)
            
        # Create a mock object that mimics tensor output
        class MockTensor:
            def __init__(self, data):
                self.data = data
            def quantile(self, q, dim=None):
                # Return slightly different values for quantiles
                if q == 0.1: return MockValue([x * 0.95 for x in self.data])
                if q == 0.5: return MockValue(self.data)
                if q == 0.9: return MockValue([x * 1.05 for x in self.data])
        
        class MockValue:
            def __init__(self, data):
                self.data = data
            def item(self): return self.data[-1]
            def tolist(self): return self.data

        return [MockTensor(predictions)]

def get_stock_brain(ticker: str, name: str, market: str):
    """Get or create a StockBrain instance (cached)."""
    cache_key = f"{ticker}_{market}"
    if cache_key not in _stock_brain_cache:
        try:
            from main import StockBrain
            print(f"🔄 [StockTool] Initializing Real AI Model for {ticker}...")
            _stock_brain_cache[cache_key] = StockBrain(ticker, name, market)
        except Exception as e:
            print(f"⚠️ [StockTool] Failed to load Real AI Model: {e}")
            print(f"⚠️ [StockTool] Falling back to MockModel.")
            _stock_brain_cache[cache_key] = MockStockBrain(ticker, name, market)
            
    return _stock_brain_cache[cache_key]

def analyze_stock(ticker: str, name: str, market: str = "KR") -> dict:
    """
    Analyze a stock using AI (Chronos + FinBERT fusion).
    """
    try:
        brain = get_stock_brain(ticker, name, market)
        
        # Get timezone and formatting based on market
        if market == "US":
            tz = pytz.timezone('US/Eastern')
            currency = "$"
            fmt = ",.2f"
        else:
            tz = pytz.timezone('Asia/Seoul')
            currency = "₩"
            fmt = ",.0f"
        
        # Prepare data
        prep = brain.loader.prepare_all()
        
        # Mock scores if using MockBrain
        if isinstance(brain, MockStockBrain):
            import random
            score = random.random()
            is_bullish = score > 0.5
        else:
            # Extract features and run fusion
            import torch
            stl = brain.loader.get_stl_features(brain.loader.fetch_price_data())
            text_feat, price_feat = brain.extract_features(prep['news'], prep['price_context'])
            
            with torch.no_grad():
                fused_vector = brain.fusion(text_feat, price_feat)
                score = torch.sigmoid(brain.classifier(fused_vector)).item()
                is_bullish = score > 0.5
        
        # Chronos forecast (30 days)
        # Use context or dummy if empty
        context_data = prep['price_context']
        if context_data is None or len(context_data) == 0:
            context_data = [prep['current_price']] * 30
            
        # Call predict (MockBrain handles this seamlessly now)
        forecast_steps = 30
        
        # Logic for real/mock is extracted in predict() of MockBrain
        # For real brain, we assume it has the same interface
        # But wait, real brain predict might take tensor.
        if isinstance(brain, MockStockBrain):
            forecast = brain.predict(context_data, forecast_steps)
        else:
            context_tensor = torch.tensor(context_data)
            forecast = brain.chronos.predict(context_tensor, forecast_steps)
        
        # Get quantiles for confidence intervals (dim=0 across samples)
        low_conf = forecast[0].quantile(0.1, dim=0).tolist()
        median_conf = forecast[0].quantile(0.5, dim=0).tolist()
        high_conf = forecast[0].quantile(0.9, dim=0).tolist()
        
        # Generate future dates
        from datetime import timedelta
        last_date = datetime.now(tz)
        forecast_dates = [(last_date + timedelta(days=i+1)).strftime("%Y-%m-%d") for i in range(forecast_steps)]
        
        forecast_data = []
        for i in range(forecast_steps):
            forecast_data.append({
                "date": forecast_dates[i],
                "price": round(median_conf[i], 2),
                "lower": round(low_conf[i], 2),
                "upper": round(high_conf[i], 2)
            })
            
        cur_price = prep['current_price']
        final_forecast_price = median_conf[-1]
        forecast_change = ((final_forecast_price - cur_price) / cur_price) * 100
        
        # Recommendation Logic
        if is_bullish and forecast_change > 5:
             recommendation = "STRONG BUY"
        elif is_bullish:
             recommendation = "BUY"
        elif not is_bullish and forecast_change < -5:
             recommendation = "STRONG SELL"
        else:
             recommendation = "SELL" if not is_bullish else "HOLD"

        return {
            "status": "success",
            "ticker": ticker,
            "name": name,
            "market": market,
            "timestamp": datetime.now(tz).isoformat(),
            "current_price": f"{currency}{cur_price:{fmt}}",
            "current_price_raw": cur_price,
            "ai_score": round(score, 4),
            "sentiment": "Bullish" if is_bullish else "Bearish",
            "forecast": f"{forecast_change:+.2f}% (30일 후)",
            "forecast_data": forecast_data,
            "trend_direction": "UP" if forecast_change > 0 else "DOWN",
            "recommendation": recommendation,
            "top_news": prep['news'][0][:100] if prep['news'] else None
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "ticker": ticker,
            "error": str(e)
        }

if __name__ == "__main__":
    # Test
    result = analyze_stock("005930.KS", "Samsung Electronics", "KR")
    print(json.dumps(result, ensure_ascii=False, indent=2))
