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
        
        return json.dumps({
            "status": "success",
            "ticker": ticker,
            "company": company,
            "valuation": valuation,
            "profitability": profitability,
            "per_share": per_share,
            "dividend": dividend,
            "growth": growth,
            "financial_health": health,
        }, ensure_ascii=False)
        
    except Exception as e:
        return json.dumps({"status": "error", "ticker": ticker, "error": str(e)})
