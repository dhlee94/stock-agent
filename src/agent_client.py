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
    GLOBAL_PLANNER_MODEL, LOCAL_REFLECTOR_MODEL, GLOBAL_REFLECTOR_MODEL, JUDGE_MODEL,
    MEMORY_COMPRESSOR_MODEL, MAX_GLOBAL_ITER,
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
        header = sec.split("\n", 1)[0]
        if "Failed -" not in header:
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
            {"role": "system", "content": load_prompt("news_analyst/system")},
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
            {"role": "system", "content": load_prompt("summarizer/system")},
            {"role": "user", "content": user_content}
        ]
        return await self._call_llm(prompt, model=SUMMARIZER_MODEL, max_tokens=8192)

    async def _call_local_reflector(self, focus: str, findings: str) -> Dict[str, Any]:
        print(f"\n🔎 [Local Reflector] Validating: {focus}")
        prompt = [
            {"role": "system", "content": load_prompt("local_reflector/system")},
            {"role": "user", "content": f"Subtask: {focus}\n\nFindings:\n{findings[:2000]}"},
        ]
        response = await self._call_llm(prompt, model=LOCAL_REFLECTOR_MODEL)
        return _parse_llm_json(response) or {"valid": True}

    async def _call_global_reflector(self, user_task: str, all_findings: str, market_facts: str = "") -> Dict[str, Any]:
        print("\n🔍 [Global Reflector] Critiquing...")
        user_content = f"Query: {user_task}\n\nFindings:\n{all_findings}"
        if market_facts:
            user_content = f"{market_facts}\n\n{user_content}"
        prompt = [
            {"role": "system", "content": load_prompt("global_reflector/system")},
            {"role": "user", "content": user_content},
        ]
        response = await self._call_llm(prompt, model=GLOBAL_REFLECTOR_MODEL, max_tokens=4096)
        critique = _parse_llm_json(response) or {"approved": True}
        if not critique.get("approved") and critique.get("critique"):
            print(f"   💡 Critique: {critique['critique']}")
        return critique

    async def _call_global_planner_defense(self, user_task: str, critique: Dict[str, Any], all_findings: str, tool_descriptions: str = "") -> Dict[str, Any]:
        print("\n🛡️ [Global Planner] Responding to critique...")
        prompt = [
            {"role": "system", "content": load_prompt("global_planner/defense", tool_capabilities=tool_descriptions)},
            {"role": "user", "content": f"Query: {user_task}\n\nCritique: {critique.get('critique', '')}"},
        ]
        response = await self._call_llm(prompt, model=GLOBAL_PLANNER_MODEL)
        defense = _parse_llm_json(response) or {"new_subtasks": []}
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
        return _parse_llm_json(response) or {"verdict": "planner"}

    async def _run_subtask(self, subtask: Dict[str, Any], session, tool_descriptions: str, semaphore: asyncio.Semaphore, user_task: str, global_plan: Dict[str, Any], critique: Optional[Dict[str, Any]] = None, previous_findings: str = "", tool_cache: Optional[Dict] = None, embedded_raw: Optional[set] = None) -> Dict[str, Any]:
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
                        if tool_name in ("stock_news", "stock_news_sentiment"):
                            interpretation = await self._call_news_analyst(tool_output)
                        elif tool_name == "stock_technical":
                            interpretation = await self._call_technical_analyst(tool_output)
                        else:
                            interpretation = await self._call_executor(step, tool_output, findings)
                        findings += f"\n### {step.get('reason', tool_name)}\n{interpretation}\n"
                    except Exception as e:
                        findings += f"\n### {tool_name}: Failed - {e}\n"
                return findings

            plan = await self._call_planner(user_task, tool_descriptions, "", extracted_intent=global_plan, subtask_focus=focus, subtask_context=subtask.get("context", ""), subtask_search_hints=subtask.get("search_hints", []), critique=critique, previous_findings=previous_findings)
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

        # Carry the prior round's critique + accumulated findings into the next
        # round's subtask planners. On iter 0 these are empty (fresh analysis);
        # from iter 1 on, the planner sees what was wrong and what was already
        # collected so it closes the gap instead of re-deriving from scratch.
        pending_critique: Optional[Dict[str, Any]] = None
        pending_findings: str = ""

        # OUT-edge of the loop. The Reflector re-judges from scratch each round,
        # so on its own a refinement that adds nothing would just be re-rejected
        # and re-spawned — the "identical results across runs" failure. We track
        # which focuses have already produced usable data (seen_valid_focuses),
        # drop re-proposed work, and stop the moment a refinement round yields no
        # NEW usable data. Whatever the Reflector flagged but we could not resolve
        # is recorded in unresolved_points and reported honestly by the Summarizer
        # rather than silently repeated or papered over.
        seen_valid_focuses: set = {f for f, ok in valid_by_focus.items() if ok}
        unresolved_points: List[str] = []
        conceded_last_round: List[str] = []

        def _critique_points(c: Dict[str, Any]) -> List[str]:
            return (c.get("weak_points") or []) + (c.get("missing_coverage") or [])

        for global_iter in range(MAX_GLOBAL_ITER):
            if global_iter > 0:
                # Drop refinement subtasks that merely re-propose work whose focus
                # already yielded usable data — that is the duplicate-block churn.
                subtasks = [st for st in subtasks
                            if st.get("focus") not in seen_valid_focuses]
                if not subtasks:
                    unresolved_points.extend(conceded_last_round)
                    outcome = "no_new_subtasks"
                    break

            results = await asyncio.gather(*[self._run_subtask(st, session, tool_descriptions, semaphore, user_task, global_plan, critique=pending_critique, previous_findings=pending_findings, tool_cache=tool_cache) for st in subtasks])
            for r in results:
                findings_by_focus[r["focus"]] = r["findings"]
                valid_by_focus[r["focus"]] = r.get("valid", True)

            new_valid = {r["focus"] for r in results if r.get("valid", True)} - seen_valid_focuses
            if global_iter > 0 and not new_valid:
                # Refinement produced no new usable data — stop spinning and flag
                # what this round was supposed to fix as unresolved.
                unresolved_points.extend(conceded_last_round)
                outcome = "no_progress"
                all_findings = _assemble_findings()
                break
            seen_valid_focuses |= new_valid

            all_findings = _assemble_findings()
            global_critique = await self._call_global_reflector(user_task, all_findings, market_facts)
            if global_critique.get("approved"):
                outcome = "approved_early" if global_iter == 0 else "approved_late"
                break
            if global_iter >= MAX_GLOBAL_ITER - 1:
                unresolved_points.extend(_critique_points(global_critique))
                outcome = "maxed"
                break
            defense = await self._call_global_planner_defense(user_task, global_critique, all_findings, tool_descriptions)
            subtasks = defense.get("new_subtasks", [])
            conceded_last_round = defense.get("concede") or _critique_points(global_critique)
            if not subtasks:
                break
            # Hand this round's critique + findings to next round's planners.
            pending_critique = global_critique
            pending_findings = all_findings

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
        if ticker and len(global_plan.get("subtasks", [])) == 1:
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
            synth_result = await self._run_subtask(
                synth_subtask, session, tool_descriptions, semaphore, user_task,
                global_plan, critique=synth_critique, previous_findings=all_findings,
                tool_cache=tool_cache)
            if synth_result.get("valid"):
                findings_by_focus[synth_result["focus"]] = synth_result["findings"]
                valid_by_focus[synth_result["focus"]] = True
                all_findings = _assemble_findings()

        summary = await self._call_summarizer(user_task, all_findings, unresolved_points)
        return summary, {"plan": json.dumps(list(findings_by_focus.keys())), "score": 0.8, "lessons": []}

    async def run_for_web(self, user_task: str) -> str:
        try:
            session, tool_descriptions = await self._ensure_mcp_session()
            global_plan = await self._call_global_planner(user_task)
            saved_result, meta = await self._run_flow(user_task, global_plan, session, tool_descriptions, "", [])
            self.memory.save_trajectory(user_task, meta["plan"], saved_result, meta["score"], meta["lessons"])
            return saved_result
        except Exception as e:
            return f"오류: {e}"

if __name__ == "__main__":
    agent = MementoAgent()
    asyncio.run(agent.run_for_web("삼성전자 어때?"))
