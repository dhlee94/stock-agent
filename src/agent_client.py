import asyncio
import os
import sys
import json
import re
import time
import random
from typing import List, Dict, Any, Optional

# Use centralized config
from config import (
    LLM_PROVIDER, LLM_MODEL,
    GEMINI_API_KEY, OPENAI_API_KEY, GROQ_API_KEY, ANTHROPIC_API_KEY,
    PLANNER_MODEL, EXECUTOR_MODEL, SUMMARIZER_MODEL,
    NEWS_ANALYST_MODEL, TECHNICAL_ANALYST_MODEL,
    GLOBAL_PLANNER_MODEL, GLOBAL_REFLECTOR_MODEL, JUDGE_MODEL,
    MEMORY_COMPRESSOR_MODEL, MAX_GLOBAL_ITER, FLOW_TIME_BUDGET_SEC,
    MAX_FOCUS_REVISIONS,
)
from database import get_setting, reembed_if_model_changed
from tools.stock.kr_listing import lookup_kr_ticker


def _resolve_active_embedding_model() -> str:
    from config import EMBEDDING_PROVIDER, EMBEDDING_MODEL, OPENAI_API_KEY, GEMINI_API_KEY
    _LOCAL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    if EMBEDDING_PROVIDER == "openai" and OPENAI_API_KEY:
        return EMBEDDING_MODEL
    if GEMINI_API_KEY:
        return EMBEDDING_MODEL
    return _LOCAL
from tools.stock.us_listing import lookup_us_ticker, is_valid_us_ticker
from tools.stock.market_utils import NAME_TO_TICKER


def _today_str() -> str:
    """Current date anchor (KST) injected into analysis prompts. Without it the
    LLMs resolve "as of today" against their training cutoff and treat stale
    fetched data (e.g. last year's guidance) as current — see news_analyst /
    global_reflector / summarizer / planner system prompts."""
    import pytz
    from datetime import datetime
    return datetime.now(pytz.timezone("Asia/Seoul")).strftime("%Y-%m-%d (%a)")

# Provider setup
_provider_clients: dict = {}
_LAST_API_CALL: dict = {}
_PROVIDER_LOCKS: dict = {}
_MIN_WAIT = {"groq": 0.5, "anthropic": 0.5, "gemini": 2.0, "openai": 2.0}
_LLM_MAX_RETRIES = int(os.environ.get("LLM_MAX_RETRIES", "3"))


def _provider_lock(provider: str) -> "asyncio.Lock":
    lock = _PROVIDER_LOCKS.get(provider)
    if lock is None:
        lock = asyncio.Lock()
        _PROVIDER_LOCKS[provider] = lock
    return lock


def _is_retryable_error(e: Exception) -> bool:
    status = (getattr(e, "status_code", None) or getattr(e, "code", None)
              or getattr(getattr(e, "response", None), "status_code", None))
    if status in (408, 409, 429, 500, 502, 503, 504):
        return True
    name = type(e).__name__.lower()
    if any(k in name for k in ("ratelimit", "timeout", "connection", "serviceunavailable",
                               "internalserver", "overloaded", "apiconnection", "unavailable")):
        return True
    msg = str(e).lower()
    return any(k in msg for k in ("rate limit", "429", "timed out", "timeout",
                                  "temporarily unavailable", "overloaded", "503",
                                  "502", "500", "connection reset", "connection error"))


def _parse_llm_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    cleaned = re.sub(r"```(?:json)?", "", text)
    m = re.search(r"\{[\s\S]*\}", cleaned)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except (ValueError, TypeError):
        return None

try:
    from google import genai as _gemini_genai
    if GEMINI_API_KEY:
        _provider_clients["gemini"] = _gemini_genai.Client(api_key=GEMINI_API_KEY)
except ImportError:
    pass

try:
    from openai import OpenAI as _OpenAI
    if OPENAI_API_KEY:
        _provider_clients["openai"] = _OpenAI(api_key=OPENAI_API_KEY)
except ImportError:
    pass

try:
    from groq import Groq as _Groq
    if GROQ_API_KEY:
        _provider_clients["groq"] = _Groq(api_key=GROQ_API_KEY)
except ImportError:
    pass

try:
    import anthropic as _anthropic_module
    if ANTHROPIC_API_KEY:
        _provider_clients["anthropic"] = _anthropic_module.Anthropic(api_key=ANTHROPIC_API_KEY)
except ImportError:
    pass

MOCK_MODE = LLM_PROVIDER not in _provider_clients


def _detect_provider(model: str) -> str:
    if model.startswith("claude-"):
        return "anthropic"
    if model.startswith("gemini-"):
        return "gemini"
    if model.startswith(("gpt-", "o1-", "o3-", "o4-")):
        return "openai"
    return "groq"

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

try:
    from .memory_store import MemoryStore, ProceduralMemory, SemanticMemory
    from .prompts import load_prompt
except ImportError:
    from memory_store import MemoryStore, ProceduralMemory, SemanticMemory
    from prompts import load_prompt

class MockLLM:
    def __init__(self):
        self.step = 0
    
    def chat(self, messages):
        self.step += 1
        if self.step == 1:
            return '{"tool": "search_web", "arguments": {"query": "latest AI news"}}'
        elif self.step == 2:
            return 'DONE: I have searched for information. Here is the summary: AI is advancing rapidly.'
        return 'DONE: Task completed.'

_KR_TICKER_RE = re.compile(r"\(\s*(\d{6})\.(KS|KQ)\s*\)")
_US_TICKER_RE = re.compile(r"\(\s*([A-Z][A-Z0-9.\-]{0,5})\s*\)")


def _resolve_us_name(name: str) -> Optional[str]:
    if not name:
        return None
    aliased = NAME_TO_TICKER.get(name) or NAME_TO_TICKER.get(name.strip())
    if aliased and not aliased.endswith((".KS", ".KQ")):
        return aliased
    try:
        return lookup_us_ticker(name)
    except Exception as e:
        print(f"   ⚠️ US ticker lookup failed for '{name}': {e}")
        return None


def _verify_kr_ticker_in_subject(intent: Dict[str, Any]) -> None:
    subject = intent.get("subject", "")
    if not isinstance(subject, str) or not subject:
        return

    m = _KR_TICKER_RE.search(subject)
    if m:
        name = subject[: m.start()].strip().rstrip(",;:-")
        if not name:
            return
        try:
            resolved = lookup_kr_ticker(name)
        except Exception as e:
            print(f"   ⚠️ KR ticker lookup failed for '{name}': {e}")
            return
        if not resolved:
            return
        llm_ticker = f"{m.group(1)}.{m.group(2)}"
        if resolved != llm_ticker:
            print(f"   🔧 Corrected KR ticker: {name} {llm_ticker} → {resolved} (KRX listing)")
            intent["subject"] = f"{name} ({resolved})"
        return

    m = _US_TICKER_RE.search(subject)
    if m:
        llm_sym = m.group(1)
        name = subject[: m.start()].strip().rstrip(",;:-")
        if not name:
            return
        resolved = _resolve_us_name(name)
        if resolved and resolved != llm_sym:
            print(f"   🔧 Corrected US ticker: {name} {llm_sym} → {resolved} (listing/alias)")
            intent["subject"] = f"{name} ({resolved})"
        elif not resolved and not is_valid_us_ticker(llm_sym):
            print(f"   ⚠️ LLM ticker {llm_sym!r} for '{name}' not found in US listings")


def _prev_period_key(level: str, current_key: str) -> str:
    from datetime import datetime, timedelta
    if level == 'weekly':
        year, week = int(current_key.split('-W')[0]), int(current_key.split('-W')[1])
        prev = datetime.fromisocalendar(year, week, 1) - timedelta(weeks=1)
        iso = prev.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    if level == 'monthly':
        year, month = int(current_key.split('-')[0]), int(current_key.split('-')[1])
        return f"{year-1}-12" if month == 1 else f"{year}-{month-1:02d}"
    return str(int(current_key) - 1)


_DIGEST_DROP_KEYS = frozenset({
    "website", "irwebsite", "url", "logo", "logo_url",
    "employees", "fulltimeemployees",
    "country", "address", "address1", "city", "state", "zip", "phone", "fax",
    "longbusinesssummary", "long_business_summary", "businesssummary", "description",
    "timestamp", "uuid", "exchange", "quotetype",
})


def _digest_tool_output(raw: str, limit: int) -> str:
    try:
        obj = json.loads(raw)
    except (ValueError, TypeError):
        return raw[:limit]

    def _prune(o):
        if isinstance(o, dict):
            return {k: _prune(v) for k, v in o.items()
                    if k.lower() not in _DIGEST_DROP_KEYS}
        if isinstance(o, list):
            return [_prune(v) for v in o]
        return o

    return json.dumps(_prune(obj), ensure_ascii=False, separators=(",", ":"))[:limit]


def _budget_findings(findings_by_focus: Dict[str, str], total_budget: int = 18000,
                     min_per_focus: int = 1000) -> str:
    items = list(findings_by_focus.items())
    if not items:
        return ""
    remaining, caps, unresolved = total_budget, {}, list(items)
    while unresolved:
        share = max(min_per_focus, remaining // len(unresolved))
        still, progressed = [], False
        for focus, text in unresolved:
            if len(text) <= share:
                caps[focus] = len(text); remaining -= len(text); progressed = True
            else:
                still.append((focus, text))
        if not progressed:
            share = max(min_per_focus, remaining // len(still)) if still else 0
            for focus, text in still:
                caps[focus] = share
            break
        unresolved = still
    parts = []
    for focus, text in items:
        cap = caps.get(focus, min_per_focus)
        body = text if len(text) <= cap else text[:cap].rstrip() + " …(trimmed)"
        parts.append(f"## [{focus}]\n{body}")
    return "\n\n".join(parts)


def _findings_usable(findings: str) -> bool:
    if not findings or not findings.strip():
        return False
    for sec in findings.split("\n### "):
        sec = sec.strip()
        if not sec:
            continue
        parts = sec.split("\n", 1)
        header = parts[0]
        body = parts[1].strip() if len(parts) > 1 else ""
        # A section counts as usable only if the tool didn't fail AND it actually
        # produced body content. A clean header with an empty body is the one gap
        # the deleted LLM local-validator used to cover; checking the body here
        # closes it deterministically instead.
        if "Failed -" not in header and body:
            return True
    return False


_TRAJ_SCORE_BY_OUTCOME = {
    "approved_early":   0.9,
    "approved_late":    0.8,
    "judge_planner":    0.75,
    "no_new_subtasks":  0.6,
    "maxed":            0.5,
    "incomplete":       0.6,
}


def _build_trajectory_meta(outcome: str, critique: Dict[str, Any],
                           findings_by_focus: Dict[str, str],
                           valid_by_focus: Dict[str, bool],
                           global_plan: Dict[str, Any]) -> Dict[str, Any]:
    score = _TRAJ_SCORE_BY_OUTCOME.get(outcome, 0.6)
    kept = [f for f, fnd in findings_by_focus.items()
            if valid_by_focus.get(f, True) and (fnd or "").strip()]
    plan = json.dumps(kept, ensure_ascii=False)
    lessons: List[str] = []
    if outcome in ("maxed", "no_new_subtasks"):
        gaps = (critique.get("missing_coverage") or []) + (critique.get("weak_points") or [])
        lessons = [f"보완 필요: {g}" for g in gaps if g][:5]
    return {"plan": plan, "score": score, "lessons": lessons}


def _market_consistency_anchor(ticker: str) -> str:
    try:
        import yfinance as yf
        from datetime import datetime
        tk = yf.Ticker(ticker)
        info = tk.info
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        shares = info.get("sharesOutstanding")
        mktcap = info.get("marketCap")
        if not (price and shares and mktcap):
            return ""
        implied = price * shares
        consistent = abs(implied - mktcap) <= 0.02 * mktcap

        lines = [ f"[VERIFIED MARKET FACTS — {ticker}]" ]
        if consistent:
            lines.append(f"- Price ${price:,.2f} × shares {shares/1e9:.3f}B = ${implied/1e9:.1f}B ≈ market cap ${mktcap/1e9:.1f}B")
        else:
            lines.append(f"- ⚠️ INCONSISTENT: price ${price:,.2f} × shares {shares/1e9:.3f}B = ${implied/1e9:.1f}B "
                         f"≠ reported market cap ${mktcap/1e9:.1f}B. One of these figures is corrupt — "
                         f"flag any per-share valuation built on them as unreliable.")
        lo, hi = info.get("fiftyTwoWeekLow"), info.get("fiftyTwoWeekHigh")
        if lo and hi:
            lines.append(f"- 52-week range ${lo:,.2f}–${hi:,.2f}; current price ${price:,.2f}")
            if price < lo or price > hi:
                lines.append(f"- ⚠️ INCONSISTENT: current price ${price:,.2f} falls outside its own "
                             f"52-week range ${lo:,.2f}–${hi:,.2f} — the price feed is likely corrupt "
                             f"(stale, split-adjusted mismatch, or wrong listing).")
        return "\n".join(lines)
    except Exception:
        return ""


def _ticker_from_subject(subject: str) -> str:
    """Extract a ticker from a global-plan subject like '넷플릭스 (NFLX)' or '삼성전자 (005930.KS)'."""
    if not subject:
        return ""
    m = _KR_TICKER_RE.search(subject)
    if m:
        return f"{m.group(1)}.{m.group(2)}"
    m = _US_TICKER_RE.search(subject)
    if m:
        return m.group(1)
    return ""


class MementoAgent:
    def __init__(self):
        self.memory = MemoryStore()
        self.semantic_memory = SemanticMemory()
        self.procedural_memory = ProceduralMemory()
        self.server_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_server.py")
        self._mcp_session = None
        self._mcp_exit_stack = None
        self._mcp_tools_desc = ""
        self._mcp_lock = None
        self._bg_tasks: set = set()
        
        if MOCK_MODE:
            print(f"[Agent] Running in MOCK mode.")
            self.llm = MockLLM()
        else:
            print(f"[Agent] Providers ready. default={LLM_PROVIDER}/{LLM_MODEL}")

        reembed_if_model_changed(_resolve_active_embedding_model())

    async def _ensure_mcp_session(self):
        if self._mcp_lock is None:
            self._mcp_lock = asyncio.Lock()

        async with self._mcp_lock:
            if self._mcp_session is not None:
                try:
                    await self._mcp_session.list_tools()
                    return self._mcp_session, self._mcp_tools_desc
                except Exception:
                    await self._reset_mcp_session()

            from contextlib import AsyncExitStack
            stack = AsyncExitStack()
            server_params = StdioServerParameters(
                command=sys.executable,
                args=[self.server_script],
                env=os.environ.copy(),
            )
            read, write = await stack.enter_async_context(stdio_client(server_params))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()

            tools_response = await session.list_tools()
            self._mcp_tools_desc = "\n".join(
                [f"- {t.name}: {t.description}" for t in tools_response.tools]
            )
            self._mcp_session = session
            self._mcp_exit_stack = stack
            return self._mcp_session, self._mcp_tools_desc

    async def _reset_mcp_session(self):
        if self._mcp_exit_stack:
            try:
                await self._mcp_exit_stack.aclose()
            except Exception:
                pass
        self._mcp_session = None
        self._mcp_exit_stack = None
        self._mcp_tools_desc = ""

    async def _call_llm(self, messages, model: str = None, max_tokens: int = 4096):
        if MOCK_MODE:
            return self.llm.chat(messages)

        effective_model = model or LLM_MODEL
        provider = _detect_provider(effective_model)

        client = _provider_clients.get(provider)
        if client is None:
            raise RuntimeError(f"No API key for provider '{provider}'")

        loop = asyncio.get_running_loop()

        async def _do_call():
            if provider in ("openai", "groq"):
                response = await loop.run_in_executor(
                    None,
                    lambda: client.chat.completions.create(
                        model=effective_model,
                        messages=messages,
                        temperature=0.3,
                        max_tokens=max_tokens,
                    )
                )
                return response.choices[0].message.content

            if provider == "anthropic":
                system_parts = [m["content"] for m in messages if m["role"] == "system"]
                chat_messages = [
                    {"role": m["role"], "content": m["content"]}
                    for m in messages if m["role"] in ("user", "assistant")
                ]
                kwargs = {
                    "model": effective_model,
                    "max_tokens": max_tokens,
                    "temperature": 0.3,
                    "messages": chat_messages,
                }
                if system_parts:
                    kwargs["system"] = [{
                        "type": "text",
                        "text": "\n\n".join(system_parts),
                        "cache_control": {"type": "ephemeral"},
                    }]
                response = await loop.run_in_executor(
                    None,
                    lambda: client.messages.create(**kwargs),
                )
                return response.content[0].text

            prompt = ""
            for msg in messages:
                role = msg["role"]
                content = msg["content"]
                if role == "system":
                    prompt += f"[System]\n{content}\n\n"
                elif role == "user":
                    prompt += f"User: {content}\n\n"
                elif role == "assistant":
                    prompt += f"Assistant: {content}\n\n"
            response = await client.aio.models.generate_content(model=effective_model, contents=prompt)
            return response.text

        last_err = None
        for attempt in range(_LLM_MAX_RETRIES + 1):
            await self._rate_limit_gate(provider)
            try:
                return await _do_call()
            except Exception as e:
                last_err = e
                if attempt >= _LLM_MAX_RETRIES or not _is_retryable_error(e):
                    raise
                backoff = min(2.0 ** attempt, 8.0) + random.uniform(0, 0.5)
                await asyncio.sleep(backoff)
        raise last_err

    async def _rate_limit_gate(self, provider: str):
        min_wait = _MIN_WAIT.get(provider, 2.0)
        loop = asyncio.get_running_loop()
        async with _provider_lock(provider):
            wait = _LAST_API_CALL.get(provider, 0.0) + min_wait - loop.time()
            if wait > 0:
                await asyncio.sleep(wait)
            _LAST_API_CALL[provider] = loop.time()

    async def _call_global_planner(self, user_task: str) -> Dict[str, Any]:
        print("\n🌐 [Global Planner] Parsing query...")
        prompt = [
            {"role": "system", "content": load_prompt("global_planner/system")},
            {"role": "user", "content": user_task},
        ]
        response = await self._call_llm(prompt, model=GLOBAL_PLANNER_MODEL)
        try:
            json_match = re.search(r"\{[\s\S]*\}", response)
            if not json_match:
                return {}
            plan = json.loads(json_match.group(0))
            _verify_kr_ticker_in_subject(plan)
            return plan
        except json.JSONDecodeError:
            return {}

    def _format_intent_context(self, intent: Dict[str, Any]) -> str:
        if not intent:
            return ""
        return load_prompt(
            "intent_extractor/context",
            subject=intent.get("subject", "(unknown)"),
            key_points=intent.get("key_points", []),
            intent_class=intent.get("intent_class", "(unknown)"),
            search_keywords=intent.get("search_keywords", []),
            forecast_horizon=0, # Legacy: always 0
            notes=intent.get("notes", ""),
        )

    async def _call_planner(self, user_task: str, tool_descriptions: str, context_examples: str, semantic_knowledge: List[str] = None, critique: Optional[Dict] = None, previous_findings: str = "", extracted_intent: Optional[Dict[str, Any]] = None, subtask_focus: str = "", subtask_context: str = "", subtask_search_hints: Optional[List[str]] = None) -> List[Dict]:
        print("\n📋 [Planner] Generating execution plan...")
        memory_context = ""
        if context_examples:
            memory_context = load_prompt("planner/memory_context", context_examples=context_examples)

        semantic_context = ""
        if semantic_knowledge:
            lessons_text = "\n".join(f"- {lesson}" for lesson in semantic_knowledge)
            semantic_context = load_prompt("planner/semantic_context", lessons_text=lessons_text)

        critique_context = ""
        if critique:
            # Keys must match the Global Reflector's output schema
            # (global_reflector/system.md): weak_points / missing_coverage.
            # Fall back to the prose critique so a point is never silently lost.
            issues = critique.get("weak_points") or []
            missing = critique.get("missing_coverage") or []
            if not issues and not missing and critique.get("critique"):
                issues = [critique["critique"]]
            prior = (previous_findings or "").strip()
            if len(prior) > 18000:
                prior = prior[:18000] + "..."
            _bullets = lambda xs: "\n".join(f"- {x}" for x in xs) if xs else "none"
            critique_context = load_prompt(
                "planner/critique_context",
                issues=_bullets(issues),
                missing=_bullets(missing),
                suggested="none",
                prior=prior if prior else "none",
            )

        intent_context = self._format_intent_context(extracted_intent or {})
        planner_system = load_prompt(
            "planner/system",
            tool_descriptions=tool_descriptions,
            intent_context=intent_context,
            memory_context=memory_context,
            semantic_context=semantic_context,
            critique_context=critique_context,
            current_date=_today_str(),
        )
        if subtask_focus:
            hints = subtask_search_hints or []
            planner_system += "\n\n" + load_prompt(
                "planner/subtask_context",
                focus=subtask_focus,
                context=subtask_context or "",
                search_hints=", ".join(hints) if hints else "(none)",
            )
        planner_prompt = [
            {"role": "system", "content": planner_system},
            {"role": "user", "content": f"Create an execution plan for: {user_task}"}
        ]
        response = await self._call_llm(planner_prompt, model=PLANNER_MODEL)
        try:
            json_match = re.search(r'\[[\s\S]*\]', response)
            if json_match:
                return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass
        return []

    async def _call_executor(self, step: Dict, tool_result: str, accumulated_context: str, tips: List[Dict] = None) -> str:
        print(f"\n🔧 [Executor] Processing: {step.get('tool', 'unknown')}")
        tips_context = ""
        if tips:
            tips_lines = [f"- {t.get('result_summary', '')[:200]}" for t in tips if t.get('result_summary')]
            if tips_lines:
                tips_context = load_prompt("executor/tips_context", tips_lines="\n".join(tips_lines))

        executor_system = load_prompt("executor/system", tips_context=tips_context)
        executor_prompt = [
            {"role": "system", "content": executor_system},
            {"role": "user", "content": f"Step: {step.get('reason', 'Execute tool')}\nTool: {step.get('tool')}\n\nTool Output: {tool_result[:2000]}"}
        ]
        return await self._call_llm(executor_prompt, model=EXECUTOR_MODEL)

    @staticmethod
    def _sentiment_guardrail(tool_result: str) -> str:
        try:
            data = json.loads(tool_result)
            dist = data.get("distribution")
            if not isinstance(dist, dict): return ""
            pos, neg = dist.get("positive"), dist.get("negative")
            if isinstance(pos, (int, float)) and isinstance(neg, (int, float)):
                gap = abs(pos - neg) * 100
                if "neutral" not in dist and gap < 15.0:
                    return f"Sentiment gap: {gap:.1f}pp < 15.0pp → Signal forced to NEUTRAL."
        except: pass
        return ""

    async def _call_news_analyst(self, tool_result: str) -> str:
        print("\n📰 [News Analyst] Interpreting...")
        guardrail = self._sentiment_guardrail(tool_result)
        user_content = f"Analyze:\n\n{tool_result[:6000]}"
        if guardrail: user_content = f"{guardrail}\n\n{user_content}"
        prompt = [
            {"role": "system", "content": load_prompt("news_analyst/system", current_date=_today_str())},
            {"role": "user", "content": user_content},
        ]
        return await self._call_llm(prompt, model=NEWS_ANALYST_MODEL)

    async def _call_technical_analyst(self, tool_result: str) -> str:
        print("\n📈 [Technical Analyst] Interpreting...")
        prompt = [
            {"role": "system", "content": load_prompt("technical_analyst/system")},
            {"role": "user", "content": f"Analyze:\n\n{tool_result[:3000]}"},
        ]
        return await self._call_llm(prompt, model=TECHNICAL_ANALYST_MODEL)

    async def _call_summarizer(self, user_task: str, all_findings: str, unresolved_points: Optional[List[str]] = None) -> str:
        print("\n📊 [Summarizer] Generating final report...")
        user_content = f"Task: {user_task}\n\nFindings:\n{all_findings}"
        if unresolved_points:
            # De-dup while preserving order, then hand the analyst the open gaps
            # so the report states them as limitations instead of overstating
            # conviction. These are points the loop could not resolve.
            seen, gaps = set(), []
            for p in unresolved_points:
                if p and p not in seen:
                    seen.add(p); gaps.append(p)
            if gaps:
                gap_text = "\n".join(f"- {g}" for g in gaps)
                user_content += (
                    "\n\n[UNRESOLVED GAPS — could not be filled despite refinement attempts]\n"
                    f"{gap_text}\n"
                    "Acknowledge these explicitly in [투자의견] as limitations that lower "
                    "conviction. Do NOT fabricate data to cover them, and do NOT silently omit them."
                )
        prompt = [
            {"role": "system", "content": load_prompt("summarizer/system", current_date=_today_str())},
            {"role": "user", "content": user_content}
        ]
        return await self._call_llm(prompt, model=SUMMARIZER_MODEL, max_tokens=8192)

    async def _call_global_reflector(self, user_task: str, all_findings: str, market_facts: str = "") -> Dict[str, Any]:
        print("\n🔍 [Global Reflector] Critiquing...")
        user_content = f"Query: {user_task}\n\nFindings:\n{all_findings}"
        if market_facts:
            user_content = f"{market_facts}\n\n{user_content}"
        prompt = [
            {"role": "system", "content": load_prompt("global_reflector/system", current_date=_today_str())},
            {"role": "user", "content": user_content},
        ]
        response = await self._call_llm(prompt, model=GLOBAL_REFLECTOR_MODEL, max_tokens=4096)
        critique = _parse_llm_json(response) or {"approved": True}
        if not critique.get("approved") and critique.get("critique"):
            print(f"   💡 Critique: {critique['critique']}")
        return critique

    async def _call_global_planner_defense(self, user_task: str, critique: Dict[str, Any], all_findings: str, tool_descriptions: str = "") -> Dict[str, Any]:
        print("\n🛡️ [Global Planner] Responding to critique...")
        # The defense decides which subtasks to re-run / add, so it must see what
        # was already collected — otherwise it re-proposes work the findings
        # already contain. Truncate to stay within context budget.
        findings_excerpt = (all_findings or "").strip()
        if len(findings_excerpt) > 12000:
            findings_excerpt = findings_excerpt[:12000] + "..."
        verdicts = critique.get("subtask_verdicts") or []
        verdict_lines = "\n".join(
            f"- [{v.get('focus','')}] sufficient={v.get('sufficient')} "
            f"issues={v.get('issues') or []}"
            for v in verdicts
        ) or "(none)"
        user_content = (
            f"Query: {user_task}\n\n"
            f"Critique: {critique.get('critique', '')}\n\n"
            f"Per-subtask verdicts:\n{verdict_lines}\n\n"
            f"Current findings:\n{findings_excerpt or '(none)'}"
        )
        prompt = [
            {"role": "system", "content": load_prompt("global_planner/defense", tool_capabilities=tool_descriptions)},
            {"role": "user", "content": user_content},
        ]
        response = await self._call_llm(prompt, model=GLOBAL_PLANNER_MODEL)
        defense = _parse_llm_json(response) or {"revise": [], "new_subtasks": []}
        defense.setdefault("revise", [])
        defense.setdefault("new_subtasks", [])
        if defense.get("defense"):
            print(f"   🛡️ Defense: {defense['defense']}")
        return defense

    async def _call_judge(self, user_task: str, critique: Dict[str, Any], defense: Dict[str, Any], tool_descriptions: str = "") -> Dict[str, Any]:
        print("\n⚖️ [Judge] Evaluating...")
        prompt = [
            {"role": "system", "content": load_prompt("judge/system", tool_capabilities=tool_descriptions)},
            {"role": "user", "content": f"Query: {user_task}"},
        ]
        response = await self._call_llm(prompt, model=JUDGE_MODEL)
        verdict = _parse_llm_json(response) or {"verdict": "planner"}
        winner = verdict.get("verdict", "planner")
        icon = "🛡️" if winner == "planner" else "🔍"
        print(f"   {icon} Verdict: {winner.upper()}")
        if verdict.get("reason"):
            print(f"   ⚖️ Reason: {verdict['reason']}")
        if verdict.get("valid_critique_points"):
            print(f"   ✅ Valid points: {verdict['valid_critique_points']}")
        if verdict.get("invalid_critique_points"):
            print(f"   ❌ Dismissed/out-of-scope: {verdict['invalid_critique_points']}")
        return verdict

    async def _run_subtask(self, subtask: Dict[str, Any], session, tool_descriptions: str, semaphore: asyncio.Semaphore, user_task: str, global_plan: Dict[str, Any], critique: Optional[Dict[str, Any]] = None, previous_findings: str = "", tool_cache: Optional[Dict] = None, embedded_raw: Optional[set] = None, context_examples: str = "", semantic_knowledge: Optional[List[str]] = None) -> Dict[str, Any]:
        async with semaphore:
            focus = subtask.get("focus", "")
            print(f"\n📌 [Subtask] Starting: {focus}")
            if tool_cache is None: tool_cache = {}

            async def _cached_call_tool(tool_name: str, args: Dict, key: str):
                fut = tool_cache.get(key)
                if fut is None:
                    fut = asyncio.ensure_future(session.call_tool(tool_name, arguments=args))
                    tool_cache[key] = fut
                return await fut

            async def _execute_plan(plan: List[Dict]) -> str:
                findings = ""
                for step in plan:
                    tool_name = step.get("tool")
                    if not tool_name: continue
                    args = step.get("args", {})
                    key = tool_name + "|" + json.dumps(args, sort_keys=True)
                    try:
                        result = await _cached_call_tool(tool_name, args, key)
                        tool_output = result.content[0].text
                        if tool_name == "stock_news":
                            interpretation = await self._call_news_analyst(tool_output)
                        elif tool_name == "stock_technical":
                            interpretation = await self._call_technical_analyst(tool_output)
                        else:
                            # Procedural memory: prior successful runs of this tool
                            # become hints for interpreting its output. Best-effort.
                            try:
                                tips = self.procedural_memory.get_tool_tips(tool_name)
                            except Exception:
                                tips = []
                            interpretation = await self._call_executor(step, tool_output, findings, tips=tips)
                        findings += f"\n### {step.get('reason', tool_name)}\n{interpretation}\n"
                    except Exception as e:
                        findings += f"\n### {tool_name}: Failed - {e}\n"
                return findings

            plan = await self._call_planner(user_task, tool_descriptions, context_examples, semantic_knowledge=semantic_knowledge, extracted_intent=global_plan, subtask_focus=focus, subtask_context=subtask.get("context", ""), subtask_search_hints=subtask.get("search_hints", []), critique=critique, previous_findings=previous_findings)
            findings = await _execute_plan(plan)
            return {"focus": focus, "findings": findings, "valid": _findings_usable(findings)}

    async def _compress_if_needed(self):
        # Background task for memory compression
        pass

    async def _run_flow(self, user_task: str, global_plan: Dict[str, Any], session, tool_descriptions: str, context_examples: str, semantic_knowledge: List[str]) -> str:
        semaphore = asyncio.Semaphore(3)
        tool_cache: Dict[str, "asyncio.Future"] = {}
        subtasks = global_plan.get("subtasks", [])
        findings_by_focus: Dict[str, str] = {}
        valid_by_focus: Dict[str, bool] = {}
        outcome = "incomplete"

        # Deterministic market-fact anchor: price × shares ≈ market cap, 52-week
        # range. Fed to the Reflector as authoritative ground truth so it can flag
        # internal inconsistencies (e.g. a corrupt share count) instead of relying
        # on stale prior knowledge it is otherwise told to distrust.
        ticker = _ticker_from_subject(global_plan.get("subject", ""))
        market_facts = _market_consistency_anchor(ticker) if ticker else ""

        def _assemble_findings() -> str:
            blocks = []
            for focus, f in findings_by_focus.items():
                if valid_by_focus.get(focus, True):
                    blocks.append(f"## [{focus}]\n{f}")
                else:
                    # Surface empty/failed blocks as explicit coverage gaps rather
                    # than letting a zero-data subtask read as a neutral signal.
                    blocks.append(f"## [{focus}] ⚠️ INCOMPLETE — no usable data retrieved; "
                                  f"treat as a coverage gap that weakens conviction, "
                                  f"not as a neutral/negative finding\n{f}")
            return "\n\n".join(blocks)

        # Per-focus revision model. Each round runs a list of work items, where a
        # work item carries its OWN critique + prior findings so a re-run focus
        # re-plans against exactly its own issues (not a global blob). A focus is
        # FROZEN once the Reflector marks it sufficient or it hits its revision
        # cap; insufficient focuses are RE-RUN in place (overwriting their block);
        # genuinely-absent angles are ADDED as new focuses. Whatever cannot be
        # resolved is recorded in unresolved_points and reported honestly by the
        # Summarizer instead of being silently repeated or papered over.
        unresolved_points: List[str] = []
        revision_count: Dict[str, int] = {}
        # (subtask, critique_for_it, previous_findings_for_it). iter 0 = original
        # plan with no critique / prior context.
        work_items: List[tuple] = [(st, None, "") for st in subtasks]
        # Critique points the CURRENT round is attempting to resolve — promoted to
        # unresolved if the round is cut short (deadline / refinement failure).
        attempting_issues: List[str] = []
        all_findings = ""
        # Most recent Reflector critique — fed to _build_trajectory_meta so the
        # episodic memory records real lessons on unresolved/maxed runs.
        last_critique: Dict[str, Any] = {}

        # Wall-clock deadline. Each refinement round spawns fresh subtasks with
        # their own tool calls + retries and can take minutes; left unbounded the
        # cumulative time blows past the web layer's request timeout and the user
        # gets nothing. Past the deadline we stop launching new work and fall
        # through to the Summarizer with whatever was collected.
        loop = asyncio.get_running_loop()
        deadline = loop.time() + FLOW_TIME_BUDGET_SEC

        def _critique_points(c: Dict[str, Any]) -> List[str]:
            return (c.get("weak_points") or []) + (c.get("missing_coverage") or [])

        for global_iter in range(MAX_GLOBAL_ITER):
            if global_iter > 0:
                if loop.time() > deadline:
                    # Out of time — keep the collected findings, flag the open
                    # gaps, and stop refining rather than risk a hard timeout.
                    unresolved_points.extend(attempting_issues)
                    outcome = "deadline"
                    break
                if not work_items:
                    # Nothing left to revise or add this round.
                    unresolved_points.extend(attempting_issues)
                    outcome = "no_new_subtasks"
                    break

            gather_coro = asyncio.gather(*[
                self._run_subtask(st, session, tool_descriptions, semaphore, user_task,
                                  global_plan, critique=crit, previous_findings=prev,
                                  tool_cache=tool_cache, context_examples=context_examples,
                                  semantic_knowledge=semantic_knowledge)
                for (st, crit, prev) in work_items])
            if global_iter == 0:
                # Core pass — must complete; the report is built on it.
                results = await gather_coro
            else:
                # A single refinement round can itself run for minutes (fresh
                # subtasks, tool retries with backoff), so the round-boundary
                # check above is not enough — time-box the round to the remaining
                # budget and keep prior findings if it overruns.
                try:
                    results = await asyncio.wait_for(gather_coro, timeout=max(1.0, deadline - loop.time()))
                except Exception as e:
                    # Timed out or the refinement round failed. The core report is
                    # already collected, so degrade gracefully: keep prior
                    # findings, flag the open gaps, and summarize.
                    print(f"   ⏱️ Refinement round stopped ({type(e).__name__}); shipping collected findings.")
                    unresolved_points.extend(attempting_issues)
                    outcome = "deadline"
                    break
            # Overwrite by focus — a re-run focus replaces its prior block in place
            # (true revision); a new focus is added.
            for r in results:
                findings_by_focus[r["focus"]] = r["findings"]
                valid_by_focus[r["focus"]] = r.get("valid", True)

            all_findings = _assemble_findings()
            global_critique = await self._call_global_reflector(user_task, all_findings, market_facts)
            last_critique = global_critique
            if global_critique.get("approved"):
                outcome = "approved_early" if global_iter == 0 else "approved_late"
                break
            if global_iter >= MAX_GLOBAL_ITER - 1:
                unresolved_points.extend(_critique_points(global_critique))
                outcome = "maxed"
                break

            defense = await self._call_global_planner_defense(user_task, global_critique, all_findings, tool_descriptions)
            # Independent arbiter of the Critic↔Planner debate. Without it the
            # Planner is both defendant and judge: any round it proposes work the
            # loop continues, any round it concedes the loop stops — its own call
            # either way. The Judge weighs the Critic's points against the
            # Planner's defense and decides whether another round is warranted.
            verdict = await self._call_judge(user_task, global_critique, defense, tool_descriptions)
            revise = defense.get("revise") or []
            new_subtasks = defense.get("new_subtasks") or []
            if verdict.get("verdict") == "planner" or (not revise and not new_subtasks):
                # Planner prevails (good enough / remaining gaps out of scope), or
                # there is no concrete follow-up work. Stop and report whatever the
                # Judge still considered valid as unresolved.
                unresolved_points.extend(
                    verdict.get("valid_critique_points")
                    or defense.get("concede")
                    or _critique_points(global_critique))
                outcome = "judge_planner"
                break

            # Build next round's work. Each revised focus carries its OWN issues
            # (from the Reflector's per-subtask verdict) and its OWN current block
            # as prior context, so its planner re-plans to fix exactly that focus.
            verdict_by_focus = {v.get("focus"): v
                                for v in (global_critique.get("subtask_verdicts") or [])}
            next_items: List[tuple] = []
            for item in revise:
                focus = item.get("focus")
                if not focus:
                    continue
                if focus not in findings_by_focus:
                    # Defense named a focus that doesn't exist — run it as new work.
                    next_items.append(({"focus": focus, "context": item.get("context", ""),
                                        "search_hints": item.get("search_hints", [])},
                                       global_critique, all_findings))
                    continue
                if revision_count.get(focus, 0) >= MAX_FOCUS_REVISIONS:
                    # Exhausted this focus's revision budget — freeze it and report
                    # its open issues rather than looping on an unfixable problem.
                    unresolved_points.extend(verdict_by_focus.get(focus, {}).get("issues") or [])
                    continue
                revision_count[focus] = revision_count.get(focus, 0) + 1
                issues = verdict_by_focus.get(focus, {}).get("issues") or [item.get("context", "")]
                focus_critique = {
                    "critique": item.get("context", ""),
                    "weak_points": issues,
                    "missing_coverage": [],
                }
                prev = f"## [{focus}]\n{findings_by_focus.get(focus, '')}"
                next_items.append(({"focus": focus, "context": item.get("context", ""),
                                    "search_hints": item.get("search_hints", [])},
                                   focus_critique, prev))
            for st in new_subtasks:
                next_items.append((st, global_critique, all_findings))

            if not next_items:
                # Everything the defense proposed was capped/invalid — stop.
                unresolved_points.extend(
                    verdict.get("valid_critique_points") or _critique_points(global_critique))
                outcome = "no_new_subtasks"
                break
            work_items = next_items
            attempting_issues = verdict.get("valid_critique_points") or _critique_points(global_critique)

        # Tier 2 — integration slot. Tier-1 subtasks run in parallel and never
        # see each other's output, so cross-cutting facts (a news catalyst that
        # should move the growth assumption, a resistance level that bounds the
        # upside) never reach the valuation. Here we run ONE more subtask seeded
        # with the converged Tier-1 findings and a synthetic critique that asks
        # for exactly that integration — reusing the critique wiring so the
        # planner sees the prior findings and can, e.g., re-run stock_dcf with a
        # catalyst-informed growth_override. Single-company queries only (a lone
        # subject with a resolved ticker); sectors/comparisons have no single
        # valuation to integrate into.
        if ticker and len(global_plan.get("subtasks", [])) == 1 and loop.time() < deadline:
            synth_critique = {
                "weak_points": [
                    "수집된 뉴스·촉매가 밸류에이션에 정량 반영되지 않음 — 성장 전망을 "
                    "의미있게 바꾸는 촉매가 있으면 stock_dcf를 growth_override로 재실행해 "
                    "촉매 반영 내재가치를 산출",
                    "기술적 저항선/지지선이 리스크·리워드 시나리오에 반영되지 않음",
                    "센티먼트·뉴스 커버리지 공백이 컨빅션 평가에 반영되지 않음",
                ],
            }
            synth_subtask = {
                "focus": "통합 밸류에이션 및 시나리오",
                "context": ("1단계에서 이미 수집된 데이터를 교차 통합하는 단계. 새 원자료를 "
                            "폭넓게 재수집하지 말고, 모인 findings를 정량 종합하라."),
                "search_hints": [],
            }
            try:
                synth_result = await asyncio.wait_for(
                    self._run_subtask(
                        synth_subtask, session, tool_descriptions, semaphore, user_task,
                        global_plan, critique=synth_critique, previous_findings=all_findings,
                        tool_cache=tool_cache, context_examples=context_examples,
                        semantic_knowledge=semantic_knowledge),
                    timeout=max(1.0, deadline - loop.time()))
                if synth_result.get("valid"):
                    findings_by_focus[synth_result["focus"]] = synth_result["findings"]
                    valid_by_focus[synth_result["focus"]] = True
                    all_findings = _assemble_findings()
            except Exception as e:
                # Integration ran out of budget or failed; ship Tier-1 as-is.
                print(f"   ⏱️ Integration step skipped ({type(e).__name__}); shipping Tier-1 report.")

        summary = await self._call_summarizer(user_task, all_findings, unresolved_points)
        # Real outcome-derived score + lessons (was hardcoded 0.8/[], which froze
        # the episodic dedup/overwrite gate and starved semantic memory of lessons).
        meta = _build_trajectory_meta(outcome, last_critique, findings_by_focus,
                                      valid_by_focus, global_plan)
        return summary, meta

    @staticmethod
    def _format_trajectory_examples(trajectories: List[Dict[str, Any]]) -> str:
        """Render recalled past runs as compact priming context for the planner."""
        blocks = []
        for t in trajectories or []:
            lessons = t.get("lessons") or []
            lesson_txt = "; ".join(lessons) if lessons else "(none)"
            blocks.append(
                f"### Past run: {t.get('task','')}\n"
                f"- focuses: {t.get('plan','')}\n"
                f"- score: {t.get('score','?')}\n"
                f"- lessons: {lesson_txt}"
            )
        return "\n\n".join(blocks)

    def _recall_memory(self, user_task: str) -> tuple:
        """Pull similar past trajectories + generalized lessons to prime planning.
        Best-effort: an embedding/DB failure must degrade to no-recall, not crash
        the run."""
        context_examples, lessons = "", []
        try:
            trajectories = self.memory.retrieve_similar(user_task, top_k=3)
            context_examples = self._format_trajectory_examples(trajectories)
        except Exception as e:
            print(f"   ⚠️ Episodic recall skipped: {e}")
        try:
            lessons = self.semantic_memory.retrieve_relevant(user_task, top_k=5) or []
        except Exception as e:
            print(f"   ⚠️ Semantic recall skipped: {e}")
        if context_examples or lessons:
            print(f"   🧠 Recalled {len(context_examples.split('### Past run:')) - 1} "
                  f"past run(s), {len(lessons)} lesson(s)")
        return context_examples, lessons

    async def run_for_web(self, user_task: str) -> str:
        try:
            session, tool_descriptions = await self._ensure_mcp_session()
            global_plan = await self._call_global_planner(user_task)
            context_examples, semantic_knowledge = self._recall_memory(user_task)
            saved_result, meta = await self._run_flow(user_task, global_plan, session, tool_descriptions, context_examples, semantic_knowledge)
            self.memory.save_trajectory(user_task, meta["plan"], saved_result, meta["score"], meta["lessons"])
            return saved_result
        except Exception as e:
            return f"오류: {e}"

if __name__ == "__main__":
    agent = MementoAgent()
    asyncio.run(agent.run_for_web("삼성전자 어때?"))
