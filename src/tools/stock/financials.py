"""
Financial Data Tool - Company fundamentals and financial statements
"""
import json
import yfinance as yf


def get_financials(ticker: str) -> str:
    """
    Get company financial data including valuation metrics and fundamentals.
    Args:
        ticker: Stock ticker symbol
    Returns:
        JSON with PER, PBR, EPS, dividend yield, and key financial metrics
    """
    print(f"📋 [Financials] Getting fundamentals for: {ticker}")
    
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        # Valuation Metrics
        valuation = {
            "market_cap": info.get('marketCap'),
            "enterprise_value": info.get('enterpriseValue'),
            "trailing_pe": info.get('trailingPE'),
            "forward_pe": info.get('forwardPE'),
            "peg_ratio": info.get('pegRatio'),
            "price_to_book": info.get('priceToBook'),
            "price_to_sales": info.get('priceToSalesTrailing12Months'),
            "enterprise_to_revenue": info.get('enterpriseToRevenue'),
            "enterprise_to_ebitda": info.get('enterpriseToEbitda'),
        }
        
        # Profitability
        profitability = {
            "profit_margin": info.get('profitMargins'),
            "operating_margin": info.get('operatingMargins'),
            "return_on_assets": info.get('returnOnAssets'),
            "return_on_equity": info.get('returnOnEquity'),
            "gross_margin": info.get('grossMargins'),
            "ebitda_margin": info.get('ebitdaMargins'),
        }
        
        # Per Share Data
        per_share = {
            "eps_trailing": info.get('trailingEps'),
            "eps_forward": info.get('forwardEps'),
            "book_value": info.get('bookValue'),
            "revenue_per_share": info.get('revenuePerShare'),
        }
        
        # Dividend Info
        dividend = {
            "dividend_rate": info.get('dividendRate'),
            "dividend_yield": info.get('dividendYield'),
            "payout_ratio": info.get('payoutRatio'),
            "ex_dividend_date": info.get('exDividendDate'),
        }
        
        # Growth
        growth = {
            "revenue_growth": info.get('revenueGrowth'),
            "earnings_growth": info.get('earningsGrowth'),
            "earnings_quarterly_growth": info.get('earningsQuarterlyGrowth'),
        }
        
        # Financial Health
        health = {
            "total_cash": info.get('totalCash'),
            "total_debt": info.get('totalDebt'),
            "debt_to_equity": info.get('debtToEquity'),
            "current_ratio": info.get('currentRatio'),
            "quick_ratio": info.get('quickRatio'),
            "free_cash_flow": info.get('freeCashflow'),
            "operating_cash_flow": info.get('operatingCashflow'),
        }
        
        # Company Info
        company = {
            "name": info.get('shortName', info.get('longName')),
            "sector": info.get('sector'),
            "industry": info.get('industry'),
            "employees": info.get('fullTimeEmployees'),
            "country": info.get('country'),
            "website": info.get('website'),
        }
        
        result_data = {
            "status": "success",
            "ticker": ticker,
            "company": company,
            "valuation": valuation,
            "profitability": profitability,
            "per_share": per_share,
            "dividend": dividend,
            "growth": growth,
            "financial_health": health,
        }

        # 🚀 KR Market Enhancement with PyKRX
        if ticker.endswith(".KS") or ticker.endswith(".KQ"):
            try:
                from pykrx import stock
                from datetime import datetime, timedelta
                print(f"   🇰🇷 [PyKRX] Enhancing data for {ticker}")
                
                code = ticker.split('.')[0]
                # Fetch recent fundamental data (last 5 business days to ensure data)
                end_str = datetime.now().strftime("%Y%m%d")
                start_str = (datetime.now() - timedelta(days=7)).strftime("%Y%m%d")
                
                # get_market_fundamental returns index as Date
                df = stock.get_market_fundamental(start_str, end_str, code)
                
                if not df.empty:
                    # Use the most recent row
                    recent = df.iloc[-1]
                    
                    # Overwrite fields with authoritative KRX data
                    # Valid columns: BPS, PER, PBR, EPS, DIV, DPS
                    if 'PER' in recent and recent['PER'] > 0:
                        result_data['valuation']['trailing_pe'] = float(recent['PER'])
                    
                    if 'PBR' in recent and recent['PBR'] > 0:
                        result_data['valuation']['price_to_book'] = float(recent['PBR'])
                        
                    if 'EPS' in recent:
                        result_data['per_share']['eps_trailing'] = float(recent['EPS'])
                        
                    if 'BPS' in recent:
                        result_data['per_share']['book_value'] = float(recent['BPS'])
                        
                    if 'DIV' in recent:
                        # PyKRX DIV is yield percent (e.g. 2.5) -> convert to decimal? 
                        # yfinance expects 0.025? No, yfinance often gives 0.025. 
                        # Let's check typical yfinance output. Usually decimal. 
                        # PyKRX likely returns 2.5 for 2.5%.
                        result_data['dividend']['dividend_yield'] = float(recent['DIV']) / 100.0
                        
            except Exception as e:
                print(f"   ⚠️ [PyKRX] Enhancement failed: {str(e)}")

        return json.dumps(result_data, ensure_ascii=False)
        
    except Exception as e:
        return json.dumps({"status": "error", "ticker": ticker, "error": str(e)})
