"""
Sector Analysis Tool - Analyze market sectors and industries
"""
import json
import yfinance as yf
from utils.response import ToolResponse


# Major Korean stock indices and ETFs by sector
KOREAN_SECTORS = {
    "반도체": ["005930.KS", "000660.KS", "042700.KS"],  # Samsung, SK Hynix, 한미반도체
    "2차전지": ["373220.KS", "006400.KS", "051910.KS"],  # LG Energy, Samsung SDI, LG Chem
    "바이오": ["207940.KS", "068270.KS", "326030.KS"],   # Samsung Biologics, Celltrion, SK Biopharmaceuticals
    "자동차": ["005380.KS", "000270.KS", "012330.KS"],   # Hyundai Motor, Kia, Hyundai Mobis
    "금융": ["105560.KS", "055550.KS", "086790.KS"],     # KB Financial, Shinhan, Hana Financial
    "인터넷": ["035720.KS", "035420.KS", "263750.KS"],   # Kakao, Naver, Pearl Abyss
    "에너지": ["015760.KS", "010950.KS", "096770.KS"],   # 한국전력, S-Oil, SK이노베이션
}

# Major US sectors (using sector ETFs)
US_SECTORS = {
    "Technology": ["AAPL", "MSFT", "NVDA", "GOOGL"],
    "Healthcare": ["JNJ", "UNH", "PFE", "LLY"],
    "Financials": ["JPM", "BAC", "GS", "V"],
    "Consumer": ["AMZN", "TSLA", "NKE", "MCD"],
    "Energy": ["XOM", "CVX", "COP", "SLB"],
}


def get_sector_analysis(sector: str = None, market: str = "KR") -> str:
    """
    Analyze a market sector or get sector overview.
    Args:
        sector: Sector name to analyze (e.g., "반도체", "Technology"). If None, returns all sectors.
        market: "KR" for Korean market, "US" for US market
    Returns:
        JSON with sector performance, top stocks, and trends
    """
    print(f"🏭 [Sector] Analyzing: {sector or 'all sectors'} in {market}")
    
    try:
        sectors = KOREAN_SECTORS if market == "KR" else US_SECTORS
        
        # If specific sector requested
        if sector and sector in sectors:
            tickers = sectors[sector]
            return _analyze_sector(sector, tickers, market)

        if sector:
            return ToolResponse.error(
                f"Unknown sector: '{sector}'",
                {"available": list(sectors.keys()), "market": market}
            )

        # Otherwise, analyze all sectors
        sector_data = []
        for sector_name, tickers in sectors.items():
            try:
                result = json.loads(_analyze_sector(sector_name, tickers, market))
                if result.get('status') == 'success':
                    sector_data.append({
                        "sector": sector_name,
                        "avg_return": result.get('summary', {}).get('avg_return_1mo'),
                        "top_stock": result.get('stocks', [{}])[0].get('ticker') if result.get('stocks') else None,
                        "market_cap_total": result.get('summary', {}).get('total_market_cap'),
                    })
            except Exception:
                continue
        
        # Sort by performance
        sector_data.sort(key=lambda x: x.get('avg_return') or 0, reverse=True)
        
        return ToolResponse.success({
            "market": market,
            "sectors": sector_data,
            "best_performing": sector_data[0]['sector'] if sector_data else None,
            "worst_performing": sector_data[-1]['sector'] if sector_data else None,
        })

    except Exception as e:
        return ToolResponse.error(str(e))


def _analyze_sector(sector_name: str, tickers: list, market: str) -> str:
    """Analyze a specific sector"""
    stocks = []
    total_market_cap = 0
    returns = []
    
    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            hist = stock.history(period="1mo")
            
            if hist.empty:
                continue
            
            prices = hist['Close'].tolist()
            monthly_return = ((prices[-1] - prices[0]) / prices[0]) * 100 if prices else 0
            
            mc = info.get('marketCap', 0)
            total_market_cap += mc or 0
            returns.append(monthly_return)
            
            stocks.append({
                "ticker": ticker,
                "name": info.get('shortName', ticker),
                "current_price": round(prices[-1], 2) if prices else None,
                "market_cap": mc,
                "return_1mo": round(monthly_return, 2),
                "pe_ratio": info.get('trailingPE'),
            })
        except Exception:
            continue
    
    if not stocks:
        return json.dumps({"status": "error", "error": f"No data for sector {sector_name}"})
    
    # Sort by market cap
    stocks.sort(key=lambda x: x.get('market_cap') or 0, reverse=True)
    
    avg_return = sum(returns) / len(returns) if returns else 0
    
    return json.dumps({
        "status": "success",
        "sector": sector_name,
        "market": market,
        "stocks": stocks,
        "summary": {
            "stock_count": len(stocks),
            "total_market_cap": total_market_cap,
            "avg_return_1mo": round(avg_return, 2),
            "trend": "bullish" if avg_return > 0 else "bearish"
        }
    }, ensure_ascii=False)
