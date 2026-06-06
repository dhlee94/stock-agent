"""
Stock Comparison Tool - Compare multiple stocks
"""
import json
import yfinance as yf
from typing import List


def compare_stocks(tickers: List[str], period: str = "1y") -> str:
    """
    Compare multiple stocks on key metrics.
    Args:
        tickers: List of stock ticker symbols to compare
        period: Period for performance comparison ("1mo", "3mo", "6mo", "1y")
    Returns:
        JSON with comparative analysis of all stocks
    """
    print(f"⚖️ [Compare] Comparing: {', '.join(tickers)}")
    
    try:
        comparisons = []
        
        for ticker in tickers[:5]:  # Limit to 5 stocks
            try:
                stock = yf.Ticker(ticker)
                info = stock.info
                hist = stock.history(period=period)
                
                if hist.empty:
                    continue
                
                prices = hist['Close'].tolist()
                start_price = prices[0]
                end_price = prices[-1]
                total_return = ((end_price - start_price) / start_price) * 100 if start_price != 0 else 0.0
                
                # Volatility: sample std dev of daily returns (annualised basis omitted intentionally)
                returns = [
                    (prices[i] - prices[i - 1]) / prices[i - 1]
                    for i in range(1, len(prices)) if prices[i - 1] != 0
                ]
                if len(returns) > 1:
                    mean_r = sum(returns) / len(returns)
                    volatility = (sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)) ** 0.5 * 100
                else:
                    volatility = 0.0
                
                comparisons.append({
                    "ticker": ticker,
                    "name": info.get('shortName', ticker),
                    "sector": info.get('sector'),
                    "current_price": round(end_price, 2),
                    "market_cap": info.get('marketCap'),
                    "pe_ratio": info.get('trailingPE'),
                    "pb_ratio": info.get('priceToBook'),
                    "dividend_yield": info.get('dividendYield'),
                    "profit_margin": info.get('profitMargins'),
                    "roe": info.get('returnOnEquity'),
                    "debt_to_equity": info.get('debtToEquity'),
                    "performance": {
                        "period": period,
                        "return_percent": round(total_return, 2),
                        "volatility_percent": round(volatility, 2),
                    }
                })
            except Exception as e:
                print(f"   ⚠️ [Compare] {ticker} skipped: {e}")
                continue
        
        if not comparisons:
            return json.dumps({"status": "error", "error": "No valid stock data found"})
        
        # Rank stocks
        rankings = {
            "best_return": sorted(comparisons, key=lambda x: x['performance']['return_percent'], reverse=True)[0]['ticker'],
            "lowest_volatility": sorted(comparisons, key=lambda x: x['performance']['volatility_percent'])[0]['ticker'],
            "lowest_pe": sorted([c for c in comparisons if c['pe_ratio']], key=lambda x: x['pe_ratio'])[0]['ticker'] if any(c['pe_ratio'] for c in comparisons) else None,
            "highest_dividend": sorted([c for c in comparisons if c['dividend_yield']], key=lambda x: x['dividend_yield'], reverse=True)[0]['ticker'] if any(c['dividend_yield'] for c in comparisons) else None,
        }
        
        return json.dumps({
            "status": "success",
            "period": period,
            "stocks": comparisons,
            "rankings": rankings,
            "summary": f"Compared {len(comparisons)} stocks over {period}"
        }, ensure_ascii=False)
        
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)})
