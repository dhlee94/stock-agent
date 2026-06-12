"""
Financial Data Tool - Company fundamentals and financial statements
"""
import logging
import yfinance as yf

from utils.response import ToolResponse
from config import KRX_ID, KRX_PW

# pykrx has a bug in its logging call (logging.info(args, kwargs) instead of
# logging.info("%s %s", args, kwargs)) that prints a noisy 50-line traceback.
# Suppress it at the source.
logging.getLogger("pykrx").setLevel(logging.CRITICAL)
logging.getLogger("pykrx.website").setLevel(logging.CRITICAL)


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
            "ticker": ticker,
            "company": company,
            "valuation": valuation,
            "profitability": profitability,
            "per_share": per_share,
            "dividend": dividend,
            "growth": growth,
            "financial_health": health,
        }

        # 🚀 KR Market Enhancement with PyKRX — needs KRX credentials.
        # Skip quietly when unset so we don't spam KRX login-failure logs;
        # the base (yfinance) fundamentals above are returned as-is.
        is_kr = ticker.endswith(".KS") or ticker.endswith(".KQ")
        if is_kr and not (KRX_ID and KRX_PW):
            print(f"   ⏭️ [PyKRX] KRX_ID/KRX_PW 미설정 — {ticker} KR 펀더멘털 보강 스킵 (yfinance 값 사용)")
        elif is_kr:
            try:
                from pykrx import stock
                from datetime import datetime, timedelta
                
                code = ticker.split('.')[0]
                # Fetch recent fundamental data
                end_str = datetime.now().strftime("%Y%m%d")
                start_str = (datetime.now() - timedelta(days=10)).strftime("%Y%m%d")
                
                print(f"   🇰🇷 [PyKRX] Enhancing data for {ticker} ({start_str} ~ {end_str})")
                
                # get_market_fundamental returns index as Date
                df = stock.get_market_fundamental(start_str, end_str, code)
                
                if df is not None and not df.empty:
                    # Use the most recent row
                    recent = df.iloc[-1]
                    
                    # Overwrite fields with authoritative KRX data if valid
                    if 'PER' in recent and isinstance(recent['PER'], (int, float)) and recent['PER'] > 0:
                        result_data['valuation']['trailing_pe'] = float(recent['PER'])

                    if 'PBR' in recent and isinstance(recent['PBR'], (int, float)) and recent['PBR'] > 0:
                        result_data['valuation']['price_to_book'] = float(recent['PBR'])
                        
                    if 'EPS' in recent:
                        result_data['per_share']['eps_trailing'] = float(recent['EPS'])
                        
                    if 'BPS' in recent:
                        result_data['per_share']['book_value'] = float(recent['BPS'])
                        
                    if 'DIV' in recent:
                        result_data['dividend']['dividend_yield'] = float(recent['DIV']) / 100.0
                    
                    print(f"   ✅ [PyKRX] Successfully enhanced {ticker} metrics")
                else:
                    print(f"   ⚠️ [PyKRX] No fundamental data returned for {ticker}")
                        
            except Exception as e:
                # Non-fatal: a pykrx/KRX data-layer hiccup (usually an outdated
                # pykrx vs. a KRX site change — empty response surfaced through
                # pykrx's buggy error logger). Base yfinance fundamentals stand.
                print(f"   ⚠️ [PyKRX] 보강 실패 (비치명적 — yfinance 값 유지): {str(e)}")

        return ToolResponse.success(result_data)

    except Exception as e:
        return ToolResponse.error(str(e), {"ticker": ticker})
