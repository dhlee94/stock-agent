"""
Stock Price Tool - Real-time stock price retrieval
"""
import json
import re
import yfinance as yf
from datetime import datetime, timedelta
import pytz
from utils.response import ToolResponse
from utils.format import attach_money_display
from .market_utils import resolve_current_price


def detect_market(ticker: str, declared: str = "KR") -> str:
    """Infer the correct market from the ticker's shape, overriding a wrong
    `declared` value.

    `market` defaults to "KR" everywhere, so when the agent omits it for a US
    ticker (e.g. NFLX) the request is routed into the Korean FinanceDataReader
    path, which returns NaN/garbage prices that then propagate silently through
    DCF and risk calculations. KR tickers are numeric, optionally suffixed
    .KS/.KQ; anything alphabetic is a US ticker regardless of what was declared.
    """
    t = ticker.strip().upper()
    base = t.split(".")[0]
    if t.endswith(".KS") or t.endswith(".KQ") or base.isdigit():
        return "KR"
    if re.fullmatch(r"[A-Z][A-Z.\-]*", base):
        return "US"
    return declared


def get_stock_price(ticker: str, market: str = "KR") -> str:
    """
    Get real-time stock price and basic info.
    Args:
        ticker: Stock ticker symbol (e.g., "005930.KS" for Samsung, "AAPL" for Apple)
        market: "KR" for Korean stocks, "US" for US stocks
    Returns:
        Standardized JSON response
    """
    # Route by the ticker's actual shape, not just the (often-defaulted) market arg.
    market = detect_market(ticker, market)
    print(f"💰 [Price] Getting price for: {ticker} (market={market})")

    try:
        # Korea Market: Use FinanceDataReader
        if market == "KR":
            import FinanceDataReader as fdr
            
            code = ticker.split('.')[0] 
            
            # Get data for the last 30 days to ensure we have at least 2 trading days
            start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
            df = fdr.DataReader(code, start=start_date)
            df = df.tail(2)
            
            if df.empty:
                return ToolResponse.error(f"Failed to fetch price data for {ticker} (KR) via FDR.")
            
            current_price = float(df['Close'].iloc[-1])
            prev_close = float(df['Close'].iloc[-2]) if len(df) > 1 else float(df['Open'].iloc[-1])
            
            change = current_price - prev_close
            change_pct = (change / prev_close) * 100 if prev_close != 0 else 0.0
            
            volume = int(df['Volume'].iloc[-1])
            day_high = float(df['High'].iloc[-1])
            day_low = float(df['Low'].iloc[-1])
            
            from .market_utils import get_company_name
            stock_name = get_company_name(ticker) or ticker

            kr_payload = {
                "ticker": ticker,
                "name": stock_name,
                "current_price": round(current_price, 0),
                "previous_close": round(prev_close, 0),
                "change": round(change, 0),
                "change_percent": round(change_pct, 2),
                "currency": "KRW",
                "volume": volume,
                "day_high": round(day_high, 0),
                "day_low": round(day_low, 0),
                "timestamp": datetime.now(pytz.timezone('Asia/Seoul')).isoformat(),
                "source": "FinanceDataReader"
            }
            attach_money_display(kr_payload, "KR",
                                 per_share_keys=("current_price", "previous_close", "change",
                                                 "day_high", "day_low"))
            return ToolResponse.success(kr_payload)

        # US Market: Use yfinance
        stock = yf.Ticker(ticker)
        info = stock.info
        # Fetch a few extra sessions: the most recent bar is often a partial/empty
        # row with a NaN Close (today's session not yet settled). Taking .iloc[-1]
        # blindly propagates that NaN downstream — that is the "invalid price: nan"
        # that breaks the risk/reward calc. Drop NaN closes and use the last valid bar.
        hist = stock.history(period="5d")
        hist = hist.dropna(subset=['Close'])

        if hist.empty:
            return ToolResponse.error(f"Failed to fetch price data for {ticker}. Check ticker symbol.")

        last = hist.iloc[-1]
        # Canonical current price via the shared resolver — the SINGLE source of the
        # extended-hours-aware rule that DCF/financials/anchor also route through, so
        # every tool agrees on one current price. In PRE/POST it returns the live
        # pre/post-market print (what Google and brokers show); history() and
        # regularMarketPrice both lag there — the $74-vs-$68 earnings gap.
        current_price, reg_price, is_extended, market_state = resolve_current_price(
            info, fallback_close=last['Close'])
        reg_prev_close = (info.get("regularMarketPreviousClose") or info.get("previousClose")
                          or (hist['Close'].iloc[-2] if len(hist) > 1 else None))

        # % change is measured against the last regular-session close so it matches
        # the brokers' quote even when current_price is an extended-hours print.
        if is_extended:
            prev_close = reg_price if reg_price is not None else reg_prev_close
        else:
            prev_close = reg_prev_close if reg_prev_close is not None else current_price

        # Intraday range/volume from the live snapshot, widened to include the
        # extended-hours print so current_price never sits outside its own reported
        # range (which would trip a false internal-inconsistency flag downstream).
        day_high = info.get("regularMarketDayHigh") or info.get("dayHigh") or last['High']
        day_low = info.get("regularMarketDayLow") or info.get("dayLow") or last['Low']
        day_volume = info.get("regularMarketVolume") or info.get("volume") or last['Volume']
        day_high = max(day_high, current_price)
        day_low = min(day_low, current_price)
        change = current_price - prev_close
        change_pct = (change / prev_close) * 100 if prev_close != 0 else 0.0

        tz = pytz.timezone('US/Eastern') if market == "US" else pytz.timezone('Asia/Seoul')
        currency = "USD" if market == "US" else "KRW"
        
        from .market_utils import get_company_name
        us_payload = {
            "ticker": ticker,
            "name": get_company_name(ticker) or info.get('shortName', info.get('longName', ticker)),
            "current_price": round(current_price, 2),
            "previous_close": round(prev_close, 2),
            "change": round(change, 2),
            "change_percent": round(change_pct, 2),
            "currency": currency,
            "volume": int(day_volume),
            "day_high": round(day_high, 2),
            "day_low": round(day_low, 2),
            "market_cap": info.get('marketCap'),
            "52_week_high": info.get('fiftyTwoWeekHigh'),
            "52_week_low": info.get('fiftyTwoWeekLow'),
            "market_state": market_state,
            "timestamp": datetime.now(tz).isoformat(),
            "source": "yfinance"
        }
        # When reporting an extended-hours price, also carry the frozen regular
        # close so the report can say "프리마켓 $67.3 (정규장 종가 $74.35)" instead of
        # silently presenting a pre-market print as the regular price.
        if is_extended and reg_price is not None:
            us_payload["regular_market_price"] = round(reg_price, 2)
        us_payload["extended_hours"] = is_extended
        attach_money_display(us_payload, market, agg_keys=("market_cap",),
                             per_share_keys=("current_price", "previous_close", "change",
                                             "day_high", "day_low", "52_week_high", "52_week_low",
                                             "regular_market_price"))
        return ToolResponse.success(us_payload)
        
    except Exception as e:
        return ToolResponse.error(f"Failed to fetch price data for {ticker}: {str(e)}")

