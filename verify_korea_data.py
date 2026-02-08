import sys
import os
import json
sys.path.append(os.getcwd())
from src.tools.stock.price import get_stock_price
from src.tools.stock.financials import get_financials

def test_kr_data():
    ticker = "005930.KS"
    print(f"🔬 Testing Data Sources for {ticker}...")
    
    # 1. Price (Expect FDR)
    print("\n[1] Stock Price (Market=KR)")
    try:
        price_json = get_stock_price(ticker, "KR")
        price_data = json.loads(price_json)
        print(f"✅ Source: {price_data.get('source', 'Unknown')}")
        print(f"💰 Price: {price_data.get('current_price')} {price_data.get('currency')}")
    except Exception as e:
        print(f"❌ Price Error: {e}")

    # 2. Financials (Expect PyKRX Enhancement)
    print("\n[2] Financials (PyKRX Enhancement)")
    try:
        fin_json = get_financials(ticker)
        fin_data = json.loads(fin_json)
        
        # Check if fields are populated
        pe = fin_data['valuation'].get('trailing_pe')
        pbr = fin_data['valuation'].get('price_to_book')
        div = fin_data['dividend'].get('dividend_yield')
        
        print(f"📊 PER: {pe}")
        print(f"📚 PBR: {pbr}")
        print(f"💸 Dividend Yield: {div}")
        
        if pe and pbr:
            print("✅ PyKRX data integration successful")
        else:
            print("⚠️ PyKRX data might be missing or yfinance fallback used")
            
    except Exception as e:
        print(f"❌ Financials Error: {e}")

if __name__ == "__main__":
    test_kr_data()
