"""
DCF (Discounted Cash Flow) intrinsic-value tool.

A lightweight FCFF DCF computed off yfinance data. Outputs a bear/base/bull
intrinsic-value range plus a margin-of-safety "buy below" price, and exposes
every assumption used. Declines cleanly when the data it needs (FCF, shares,
price) is missing — common for many KR tickers.

This is a MODEL ESTIMATE, not a precise value: DCF is highly sensitive to the
growth and discount assumptions, which is why the output is a range with the
assumptions surfaced for the analyst (and Reflector) to judge.
"""
import yfinance as yf

from utils.response import ToolResponse


def _fcf_cagr(stock):
    """Estimate FCF growth from the cash-flow statement (oldest→newest CAGR), or None."""
    try:
        cf = stock.cashflow
        if cf is None or cf.empty:
            return None
        fcf_series = None
        if "Free Cash Flow" in cf.index:
            fcf_series = cf.loc["Free Cash Flow"].dropna()
        elif "Operating Cash Flow" in cf.index and "Capital Expenditure" in cf.index:
            # CapEx is reported negative in yfinance, so OCF + CapEx = FCF
            fcf_series = (cf.loc["Operating Cash Flow"] + cf.loc["Capital Expenditure"]).dropna()
        if fcf_series is None or len(fcf_series) < 2:
            return None
        vals = list(fcf_series)[::-1]  # oldest → newest
        first, last, n = vals[0], vals[-1], len(vals) - 1
        if first <= 0 or last <= 0 or n < 1:
            return None
        return (last / first) ** (1 / n) - 1
    except Exception:
        return None


def get_dcf(ticker: str, market: str = "KR",
            projection_years: int = 5,
            terminal_growth: float = 0.025,
            equity_risk_premium: float = 0.05,
            risk_free_rate: float = 0.04,
            margin_of_safety: float = 0.25,
            growth_override=None) -> str:
    """Intrinsic value per share via a lightweight FCFF DCF with a margin of safety."""
    print(f"💰 [DCF] Valuing {ticker} (proj={projection_years}y, MOS={margin_of_safety:.0%})")
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        fcf = info.get("freeCashflow")
        shares = info.get("sharesOutstanding")
        price = info.get("currentPrice") or info.get("regularMarketPrice")

        # Graceful decline — DCF is impossible without these
        if not fcf or fcf <= 0:
            return ToolResponse.error(
                "DCF 산출 불가 — 유효한 free cash flow 데이터 없음 (음수/결측). "
                "FCF가 음수이거나 불규칙한 기업은 DCF가 부적합합니다.",
                {"ticker": ticker, "free_cash_flow": fcf},
            )
        if not shares or not price:
            return ToolResponse.error(
                "DCF 산출 불가 — 발행주식수 또는 현재가 데이터 없음",
                {"ticker": ticker, "shares_outstanding": shares, "current_price": price},
            )

        beta = info.get("beta")
        beta_used = beta if (beta and beta > 0) else 1.0
        net_debt = (info.get("totalDebt") or 0) - (info.get("totalCash") or 0)

        # Growth: override > FCF-history CAGR > revenue/earnings growth > default, capped
        if growth_override is not None:
            base_growth, growth_source = growth_override, "override"
        else:
            cagr = _fcf_cagr(stock)
            if cagr is not None:
                base_growth, growth_source = cagr, "FCF history CAGR"
            else:
                rg = info.get("revenueGrowth")
                if rg is None:
                    rg = info.get("earningsGrowth")
                if rg is not None:
                    base_growth, growth_source = rg, "revenue/earnings growth"
                else:
                    base_growth, growth_source = 0.05, "default 5% (no data)"
        base_growth = max(0.0, min(base_growth, 0.15))  # sane band

        discount_base = risk_free_rate + beta_used * equity_risk_premium

        def _intrinsic(g, r):
            r = max(r, terminal_growth + 0.01)  # discount rate must exceed terminal growth
            pv, f = 0.0, fcf
            for yr in range(1, projection_years + 1):
                f *= (1 + g)
                pv += f / ((1 + r) ** yr)
            terminal = f * (1 + terminal_growth) / (r - terminal_growth)
            pv += terminal / ((1 + r) ** projection_years)
            equity_value = pv - net_debt
            return (equity_value / shares) if equity_value > 0 else None

        scenarios = {
            "bear": _intrinsic(max(0.0, base_growth - 0.02), discount_base + 0.01),
            "base": _intrinsic(base_growth, discount_base),
            "bull": _intrinsic(min(0.15, base_growth + 0.02), discount_base - 0.01),
        }
        base_iv = scenarios["base"]
        if base_iv is None:
            return ToolResponse.error(
                "DCF 산출 불가 — 음(-)의 자기자본가치 (순부채 과다 또는 FCF 약함)",
                {"ticker": ticker, "net_debt": net_debt},
            )

        # Margin of safety: conservative buy price = base intrinsic × (1 - MOS)
        buy_below = base_iv * (1 - margin_of_safety)

        return ToolResponse.success({
            "ticker": ticker,
            "current_price": round(price, 2),
            "intrinsic_value": {k: (round(v, 2) if v is not None else None)
                                for k, v in scenarios.items()},
            "margin_of_safety_pct": round(margin_of_safety * 100, 1),
            "buy_below_price": round(buy_below, 2),
            "upside_vs_base_pct": round((base_iv - price) / price * 100, 2),
            "upside_vs_buy_below_pct": round((buy_below - price) / price * 100, 2),
            "in_buy_zone": bool(price <= buy_below),
            "assumptions": {
                "fcf_ttm": fcf,
                "growth_rate_pct": round(base_growth * 100, 2),
                "growth_source": growth_source,
                "discount_rate_pct": round(discount_base * 100, 2),
                "beta_used": round(beta_used, 2),
                "beta_was_default": not (beta and beta > 0),
                "risk_free_rate_pct": round(risk_free_rate * 100, 2),
                "equity_risk_premium_pct": round(equity_risk_premium * 100, 2),
                "terminal_growth_pct": round(terminal_growth * 100, 2),
                "projection_years": projection_years,
                "net_debt": net_debt,
                "shares_outstanding": shares,
            },
            "method": ("Lightweight FCFF DCF. Discount rate = CAPM cost of equity used as a "
                       "WACC proxy. Model estimate — judge against the bear/bull range and the "
                       "assumptions above, not as a precise target."),
        })
    except Exception as e:
        return ToolResponse.error(str(e), {"ticker": ticker})
