"""
DCF (Discounted Cash Flow) intrinsic-value tool.

A lightweight two-stage FCFF DCF computed off yfinance data: stage-1 growth is
held for a high-growth window, then faded linearly to terminal growth over a
10-year explicit horizon, and discounted at a WACC proxy. Outputs a bear/base/bull
intrinsic-value range plus a margin-of-safety "buy below" price, and exposes
every assumption used. Declines cleanly when the data it needs (FCF, shares,
price) is missing — common for many KR tickers.

This is a MODEL ESTIMATE, not a precise value: DCF is highly sensitive to the
growth and discount assumptions, which is why the output is a range with the
assumptions surfaced for the analyst (and Reflector) to judge.
"""
import yfinance as yf

from utils.response import ToolResponse
from utils.format import attach_money_display
from .market_utils import get_company_name


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


def _reliable_fcf(stock, info):
    """Return (fcf, source) using a sane Free Cash Flow, or (None, reason).

    yfinance's info['freeCashflow'] is sometimes corrupted — e.g. it can exceed
    operating cash flow, which is impossible (FCF = OCF − CapEx, CapEx ≥ 0). A bad
    FCF silently inflates the whole DCF. So prefer the cash-flow statement
    (authoritative) and accept info['freeCashflow'] only when it passes a
    plausibility gate (must not exceed operating cash flow).
    """
    # 1) Authoritative: latest from the cash-flow statement.
    try:
        cf = stock.cashflow
        if cf is not None and not cf.empty:
            if "Free Cash Flow" in cf.index:
                s = cf.loc["Free Cash Flow"].dropna()
                if len(s) and float(s.iloc[0]) > 0:
                    return float(s.iloc[0]), "cash-flow statement (Free Cash Flow)"
            if "Operating Cash Flow" in cf.index and "Capital Expenditure" in cf.index:
                ocf_s = cf.loc["Operating Cash Flow"].dropna()
                capex_s = cf.loc["Capital Expenditure"].dropna()
                if len(ocf_s) and len(capex_s):
                    v = float(ocf_s.iloc[0]) + float(capex_s.iloc[0])  # CapEx is negative
                    if v > 0:
                        return v, "OCF + CapEx (cash-flow statement)"
    except Exception:
        pass
    # 2) info['freeCashflow'] — only when plausible (≤ operating cash flow).
    fcf = info.get("freeCashflow")
    ocf = info.get("operatingCashflow")
    if fcf and fcf > 0:
        if ocf and fcf > ocf:
            return None, (f"info.freeCashflow ({fcf:,.0f}) exceeds operating cash flow "
                          f"({ocf:,.0f}); impossible — discarded")
        return float(fcf), "info.freeCashflow"
    return None, "no valid free cash flow data"


def get_dcf(ticker: str, market: str = "KR",
            projection_years: int = 10,
            high_growth_years: int = 3,
            terminal_growth: float = 0.025,
            equity_risk_premium: float = 0.05,
            risk_free_rate: float = 0.04,
            tax_rate: float = 0.21,
            margin_of_safety: float = 0.25,
            growth_override=None) -> str:
    """Intrinsic value per share via a lightweight two-stage FCFF DCF with a margin of safety."""
    print(f"💰 [DCF] Valuing {ticker} (proj={projection_years}y, MOS={margin_of_safety:.0%})")
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        fcf, fcf_source = _reliable_fcf(stock, info)
        shares = info.get("sharesOutstanding")
        price = info.get("currentPrice") or info.get("regularMarketPrice")

        # Graceful decline — DCF is impossible without a sane FCF
        if not fcf or fcf <= 0:
            return ToolResponse.error(
                "DCF 산출 불가 — 유효한 free cash flow 데이터 없음 (음수/결측/비정상). "
                f"사유: {fcf_source}. FCF가 음수이거나 불규칙한 기업은 DCF가 부적합합니다.",
                {"ticker": ticker, "free_cash_flow": fcf, "fcf_source": fcf_source},
            )
        if not shares or not price:
            return ToolResponse.error(
                "DCF 산출 불가 — 발행주식수 또는 현재가 데이터 없음",
                {"ticker": ticker, "shares_outstanding": shares, "current_price": price},
            )

        # Share-count integrity check. marketCap and price are the two most
        # reliably-quoted fields, and marketCap / price is definitionally the
        # share count; sharesOutstanding is the field most prone to unit/stale
        # glitches. When sharesOutstanding diverges materially from marketCap /
        # price, trust the latter and flag it — an unflagged share-count error
        # corrupts every per-share output (intrinsic value, buy-below price).
        # NOTE: this only catches a *lone* corrupt share count. If price and
        # shares are both off by the same factor they cancel in marketCap and
        # pass this check; that class is caught instead by the 52-week-range
        # sanity check in _market_consistency_anchor (agent_client.py).
        shares_note = None
        mktcap = info.get("marketCap")
        if mktcap and price:
            implied_shares = mktcap / price
            if abs(shares - implied_shares) > 0.05 * implied_shares:
                shares_note = (
                    f"발행주식수 정합성 경고: 보고된 sharesOutstanding {shares:,.0f}이 "
                    f"marketCap/price로 역산한 {implied_shares:,.0f}와 "
                    f"{abs(shares - implied_shares) / implied_shares:.0%} 괴리. "
                    f"시가총액 기준값으로 대체함."
                )
                print(f"   🔧 [DCF] {shares_note}")
                shares = implied_shares

        beta = info.get("beta")
        beta_source = beta if (beta and beta > 0) else 1.0
        # Blume adjustment: pull the raw (noisy, often stale) beta toward the market
        # mean of 1.0 — adj = 0.67·raw + 0.33·1.0. A single spurious beta swings WACC
        # and dominates the whole DCF (e.g. NFLX raw β=1.52 → WACC 11.2% → fair $57;
        # Blume β=1.35 → WACC 10.4% → fair $64, closer to consensus). Symmetric, so it
        # tames both too-high and too-low betas across every ticker.
        beta_used = 0.67 * beta_source + 0.33 * 1.0
        net_debt = (info.get("totalDebt") or 0) - (info.get("totalCash") or 0)

        # Growth inputs — compute BOTH the FCF-history CAGR and revenue/earnings
        # growth, so a divergence between them can be flagged and hedged below.
        fcf_cagr = _fcf_cagr(stock)
        rev_growth = info.get("revenueGrowth")
        if rev_growth is None:
            rev_growth = info.get("earningsGrowth")

        def _cap_growth(g):
            return max(0.0, min(g, 0.25))  # sane stage-1 band

        DIVERGENCE_THRESHOLD_PP = 0.05

        # Base stage-1 rate selection. Prefer an explicit override; otherwise the
        # FCF-history CAGR — UNLESS it diverges materially ABOVE revenue growth, in
        # which case the FCF CAGR is treated as an unjustified transient swing (not
        # a durable growth rate) and the more conservative revenue growth anchors
        # the base case. Without this, a one-off FCF surge capped at 25% becomes the
        # headline base case (e.g. NFLX 25% vs ~16% revenue), overstating intrinsic
        # value; the FCF-synced figure is still surfaced as the optimistic end of
        # the range in growth_consistency below.
        if growth_override is not None:
            base_growth, growth_source = growth_override, "override"
        elif (fcf_cagr is not None and rev_growth is not None
              and _cap_growth(fcf_cagr) - _cap_growth(rev_growth) > DIVERGENCE_THRESHOLD_PP):
            base_growth, growth_source = rev_growth, "revenue growth (FCF CAGR diverged high — discounted)"
        elif fcf_cagr is not None:
            base_growth, growth_source = fcf_cagr, "FCF history CAGR"
        elif rev_growth is not None:
            base_growth, growth_source = rev_growth, "revenue/earnings growth"
        else:
            base_growth, growth_source = 0.05, "default 5% (no data)"
        base_growth = _cap_growth(base_growth)

        # Discount at a WACC proxy, not raw cost of equity: discounting FCFF (a
        # pre-financing cash flow) at the equity-only rate over-penalizes levered
        # firms and systematically understates intrinsic value. CAPM cost of equity +
        # an after-tax cost of debt (~150bp credit spread), weighted by market values.
        total_debt = info.get("totalDebt") or 0
        equity_mv = price * shares
        cost_of_equity = risk_free_rate + beta_used * equity_risk_premium
        after_tax_cost_of_debt = (risk_free_rate + 0.015) * (1 - tax_rate)
        v = equity_mv + total_debt
        wacc = (((equity_mv / v) * cost_of_equity + (total_debt / v) * after_tax_cost_of_debt)
                if (v > 0 and total_debt > 0) else cost_of_equity)
        discount_base = wacc

        n_high = max(1, min(high_growth_years, projection_years))
        fade_steps = projection_years - n_high

        def _growth_in_year(yr, g):
            """Two-stage growth: hold g through the high-growth stage, then fade
            linearly to terminal_growth so the explicit period lands smoothly into
            perpetuity (no abrupt growth→terminal cliff). A 5-year-only horizon used
            to truncate the runway of genuine growers; the fade restores it without
            assuming elevated growth forever."""
            if yr <= n_high or fade_steps <= 0:
                return g
            t = (yr - n_high) / fade_steps          # (0, 1]; == 1 in the final year
            return g + (terminal_growth - g) * t

        def _intrinsic(g, r):
            r = max(r, terminal_growth + 0.01)  # discount rate must exceed terminal growth
            pv, f = 0.0, fcf
            for yr in range(1, projection_years + 1):
                f *= (1 + _growth_in_year(yr, g))
                pv += f / ((1 + r) ** yr)
            terminal = f * (1 + terminal_growth) / (r - terminal_growth)
            pv += terminal / ((1 + r) ** projection_years)
            equity_value = pv - net_debt
            return (equity_value / shares) if equity_value > 0 else None

        scenarios = {
            "bear": _intrinsic(max(0.0, base_growth - 0.02), discount_base + 0.01),
            "base": _intrinsic(base_growth, discount_base),
            "bull": _intrinsic(min(0.30, base_growth + 0.02), discount_base - 0.01),
        }
        base_iv = scenarios["base"]
        if base_iv is None:
            return ToolResponse.error(
                "DCF 산출 불가 — 음(-)의 자기자본가치 (순부채 과다 또는 FCF 약함)",
                {"ticker": ticker, "net_debt": net_debt},
            )

        # Consistency guard: when FCF-history growth and revenue growth diverge
        # sharply (e.g. NFLX FCF CAGR capped at 25% vs ~16% revenue), report BOTH
        # the revenue-synced (conservative) and FCF-synced (optimistic) intrinsic
        # values so the output is always a hedged RANGE, never a lone number. The
        # base case is anchored to the conservative rate above; this surfaces the
        # other end explicitly. Skipped when the caller passed an explicit override.
        growth_consistency = None
        if fcf_cagr is not None and rev_growth is not None and growth_override is None:
            fcf_capped = _cap_growth(fcf_cagr)
            rev_capped = _cap_growth(rev_growth)
            divergence = fcf_capped - rev_capped
            if abs(divergence) > DIVERGENCE_THRESHOLD_PP:
                conservative_iv = _intrinsic(rev_capped, discount_base)
                optimistic_iv = _intrinsic(fcf_capped, discount_base)
                growth_consistency = {
                    "diverged": True,
                    "fcf_cagr_pct": round(fcf_cagr * 100, 2),
                    "revenue_growth_pct": round(rev_growth * 100, 2),
                    "divergence_pp": round(divergence * 100, 2),
                    "base_growth_used_pct": round(base_growth * 100, 2),
                    "base_growth_source": growth_source,
                    "conservative_iv_revenue_synced": round(conservative_iv, 2) if conservative_iv is not None else None,
                    "optimistic_iv_fcf_synced": round(optimistic_iv, 2) if optimistic_iv is not None else None,
                    "conservative_buy_below": (round(conservative_iv * (1 - margin_of_safety), 2)
                                               if conservative_iv is not None else None),
                    "note": ("FCF-history CAGR and revenue growth diverge by >5pp. Intrinsic value "
                             "is a RANGE between the revenue-synced (conservative) and FCF-synced "
                             "(optimistic) values; the base case is anchored to the conservative rate."),
                }

        # Headline fair value. When FCF-history and revenue growth diverge, the
        # honest anchor is the MIDPOINT of the conservative (revenue-synced) and
        # optimistic (FCF-synced) intrinsic values — NOT the conservative extreme
        # alone. Leading with the low end produced absurd targets (e.g. NFLX $42
        # fair / $31.63 buy-below on a $69 stock) that make the model look broken
        # and drive the Reflector to loop "reconciling" a price-vs-value gap that is
        # really just growth being priced in. The full range stays visible below.
        if growth_consistency and growth_consistency.get("optimistic_iv_fcf_synced") is not None:
            fair_low = growth_consistency["conservative_iv_revenue_synced"]
            fair_high = growth_consistency["optimistic_iv_fcf_synced"]
            fair_value = (fair_low + fair_high) / 2.0
        else:
            fair_low = fair_high = None
            fair_value = base_iv

        # Margin of safety: conservative buy price = fair value × (1 - MOS)
        buy_below = fair_value * (1 - margin_of_safety)

        _mkt = "KR" if (ticker.endswith(".KS") or ticker.endswith(".KQ")) else "US"
        intrinsic = {k: (round(v, 2) if v is not None else None) for k, v in scenarios.items()}
        # Surface the divergence-adjusted fair value + range as first-class fields so
        # the report leads with them instead of the lone conservative "base".
        intrinsic["fair_value"] = round(fair_value, 2)
        if fair_low is not None:
            intrinsic["range_low"] = round(fair_low, 2)
            intrinsic["range_high"] = round(fair_high, 2)
        attach_money_display(intrinsic, _mkt,
                             per_share_keys=("bear", "base", "bull",
                                             "fair_value", "range_low", "range_high"))
        if growth_consistency:
            attach_money_display(growth_consistency, _mkt,
                                 per_share_keys=("conservative_iv_revenue_synced",
                                                 "optimistic_iv_fcf_synced", "conservative_buy_below"))
        assumptions = {
                "fcf_ttm": fcf,
                "fcf_source": fcf_source,
                "stage1_growth_pct": round(base_growth * 100, 2),
                "growth_source": growth_source,
                "high_growth_years": n_high,
                "fade_years": fade_steps,
                "terminal_growth_pct": round(terminal_growth * 100, 2),
                "discount_rate_pct": round(discount_base * 100, 2),
                "discount_basis": "WACC" if total_debt > 0 else "cost of equity (no debt)",
                "cost_of_equity_pct": round(cost_of_equity * 100, 2),
                "after_tax_cost_of_debt_pct": round(after_tax_cost_of_debt * 100, 2),
                "beta_raw": round(beta, 2) if (beta and beta > 0) else None,
                "beta_used": round(beta_used, 2),
                "beta_adjustment": "Blume (0.67·raw + 0.33·1.0)",
                "beta_was_default": not (beta and beta > 0),
                "risk_free_rate_pct": round(risk_free_rate * 100, 2),
                "equity_risk_premium_pct": round(equity_risk_premium * 100, 2),
                "projection_years": projection_years,
                "net_debt": net_debt,
                "shares_outstanding": shares,
                "shares_note": shares_note,
        }
        attach_money_display(assumptions, _mkt, agg_keys=("fcf_ttm", "net_debt"))

        payload = {
            "ticker": ticker,
            "company_name": get_company_name(ticker),
            "current_price": round(price, 2),
            "intrinsic_value": intrinsic,
            "margin_of_safety_pct": round(margin_of_safety * 100, 1),
            "fair_value": round(fair_value, 2),
            "buy_below_price": round(buy_below, 2),
            "upside_vs_fair_pct": round((fair_value - price) / price * 100, 2),
            "upside_vs_base_pct": round((base_iv - price) / price * 100, 2),
            "upside_vs_buy_below_pct": round((buy_below - price) / price * 100, 2),
            "in_buy_zone": bool(price <= buy_below),
            "growth_consistency": growth_consistency,
            "assumptions": assumptions,
            "method": ("Lightweight two-stage FCFF DCF: stage-1 growth held for "
                       "high_growth_years, then faded linearly to terminal growth over the "
                       "remaining years; discounted at a WACC proxy (CAPM cost of equity + "
                       "after-tax cost of debt, market-value weighted). Model estimate — judge "
                       "against the range and assumptions, not as a precise target. When growth_"
                       "consistency.diverged is true, `fair_value` is the MIDPOINT of the "
                       "conservative (revenue-synced) and optimistic (FCF-synced) intrinsic "
                       "values — lead with fair_value and the range_low–range_high band, NOT the "
                       "lone conservative `base`. A fair value below the current price is a normal "
                       "'growth priced in / possibly rich' signal, not a model error."),
        }
        attach_money_display(payload, _mkt,
                             per_share_keys=("current_price", "fair_value", "buy_below_price"))
        return ToolResponse.success(payload)
    except Exception as e:
        return ToolResponse.error(str(e), {"ticker": ticker})
