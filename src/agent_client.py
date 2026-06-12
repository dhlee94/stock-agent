import asyncio
import os
import sys
import json
import re
import time
from typing import List, Dict, Any, Optional

# Use centralized config
from config import (
    LLM_PROVIDER, LLM_MODEL,
    GEMINI_API_KEY, OPENAI_API_KEY, GROQ_API_KEY, ANTHROPIC_API_KEY,
    PLANNER_MODEL, EXECUTOR_MODEL, SUMMARIZER_MODEL,
    NEWS_ANALYST_MODEL, TECHNICAL_ANALYST_MODEL, FORECAST_INTERPRETER_MODEL,
    GLOBAL_PLANNER_MODEL, LOCAL_REFLECTOR_MODEL, GLOBAL_REFLECTOR_MODEL, JUDGE_MODEL,
    MEMORY_COMPRESSOR_MODEL, MAX_GLOBAL_ITER,
)
from database import get_setting, reembed_if_model_changed
from tools.stock.kr_listing import lookup_kr_ticker


def _resolve_active_embedding_model() -> str:
    """Return the embedding model name that MemoryStore._get_embedding will use.

    Mirrors the provider priority in MemoryStore._get_embedding:
      1. OpenAI  (if EMBEDDING_PROVIDER=openai and key present)
      2. Gemini  (if key present — actual call may still fall back on error)
      3. Local multilingual fallback
    No live API test — avoids startup latency and rate-limit hits.
    reembed_if_model_changed will report any embedding errors at re-embed time.
    """
    from config import EMBEDDING_PROVIDER, EMBEDDING_MODEL, OPENAI_API_KEY, GEMINI_API_KEY
    _LOCAL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    if EMBEDDING_PROVIDER == "openai" and OPENAI_API_KEY:
        return EMBEDDING_MODEL
    if GEMINI_API_KEY:
        return EMBEDDING_MODEL   # Gemini key present → assume it works
    return _LOCAL
from tools.stock.us_listing import lookup_us_ticker, is_valid_us_ticker
from tools.stock.market_utils import NAME_TO_TICKER

# Provider setup — initialize every provider that has an API key so
# per-agent model overrides can freely mix providers.
_provider_clients: dict = {}
_LAST_API_CALL: dict = {}   # per-provider rate limiting
_MIN_WAIT = {"groq": 0.5, "anthropic": 0.5, "gemini": 2.0, "openai": 2.0}

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
    """Infer the API provider from the model name prefix."""
    if model.startswith("claude-"):
        return "anthropic"
    if model.startswith("gemini-"):
        return "gemini"
    if model.startswith(("gpt-", "o1-", "o3-", "o4-")):
        return "openai"
    return "groq"  # llama-*, mixtral-*, etc.

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Handle both relative and absolute imports
try:
    from .memory_store import MemoryStore, ProceduralMemory, SemanticMemory
    from .prompts import load_prompt
except ImportError:
    from memory_store import MemoryStore, ProceduralMemory, SemanticMemory
    from prompts import load_prompt

class MockLLM:
    """A simple mock LLM for demo purposes when no API key is set."""
    def __init__(self):
        self.step = 0
    
    def chat(self, messages):
        self.step += 1
        if self.step == 1:
            return '{"tool": "search_web", "arguments": {"query": "latest AI news"}}'
        elif self.step == 2:
            return 'DONE: I have searched for information. Here is the summary: AI is advancing rapidly.'
        return 'DONE: Task completed.'

# Intent-extractor LLMs hallucinate tickers for names outside the small
# hardcoded NAME_TO_TICKER map. We re-resolve the company name from
# `subject` against authoritative listings (KRX for .KS/.KQ, NASDAQ/NYSE/AMEX
# for US) and overwrite the LLM's ticker whenever the listing disagrees.
_KR_TICKER_RE = re.compile(r"\(\s*(\d{6})\.(KS|KQ)\s*\)")
_US_TICKER_RE = re.compile(r"\(\s*([A-Z][A-Z0-9.\-]{0,5})\s*\)")


def _resolve_us_name(name: str) -> Optional[str]:
    """Resolve a US company name via curated alias map first, then listing."""
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
    """Return the period key immediately before current_key for the given level."""
    from datetime import datetime, timedelta
    if level == 'weekly':
        year, week = int(current_key.split('-W')[0]), int(current_key.split('-W')[1])
        prev = datetime.fromisocalendar(year, week, 1) - timedelta(weeks=1)
        iso = prev.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    if level == 'monthly':
        year, month = int(current_key.split('-')[0]), int(current_key.split('-')[1])
        return f"{year-1}-12" if month == 1 else f"{year}-{month-1:02d}"
    return str(int(current_key) - 1)  # yearly


class MementoAgent:
    def __init__(self):
        self.memory = MemoryStore()
        self.semantic_memory = SemanticMemory()
        self.procedural_memory = ProceduralMemory()
        self.server_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_server.py")
        # MCP 싱글톤 세션 — Moirai 콜드 스타트를 최초 1회로 제한
        self._mcp_session = None
        self._mcp_exit_stack = None
        self._mcp_tools_desc = ""
        self._mcp_lock = None  # lazy: 이벤트 루프 없이 __init__에서 생성 불가
        
        if MOCK_MODE:
            print(f"[Agent] Running in MOCK mode (no API key for {LLM_PROVIDER}).")
            self.llm = MockLLM()
        else:
            available = ", ".join(
                f"{p}({v.__class__.__name__})" for p, v in _provider_clients.items()
            )
            print(f"[Agent] Providers ready: {available} | default={LLM_PROVIDER}/{LLM_MODEL}")

        # Re-embed stored memories if embedding model changed — runs once after
        # all memory stores are initialized to avoid DB lock contention at import time
        reembed_if_model_changed(_resolve_active_embedding_model())

    async def _ensure_mcp_session(self):
        """싱글톤 MCP 세션 반환. 죽어있으면 재생성."""
        if self._mcp_lock is None:
            self._mcp_lock = asyncio.Lock()

        async with self._mcp_lock:
            if self._mcp_session is not None:
                try:
                    await self._mcp_session.list_tools()
                    return self._mcp_session, self._mcp_tools_desc
                except Exception:
                    print("🔌 [MCP] Session dead — recreating...")
                    await self._reset_mcp_session()

            from contextlib import AsyncExitStack
            stack = AsyncExitStack()
            server_params = StdioServerParameters(
                command=sys.executable,
                args=[self.server_script],
                # Forward the full parent environment so MCP tools see API keys
                # (NAVER, KRX, etc.). MCP's stdio client otherwise passes only a
                # minimal default env, and .env is not in the Docker image
                # (dockerignored) — so the subprocess would see no keys at all.
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
            print("🔌 [MCP] New persistent session created")
            return self._mcp_session, self._mcp_tools_desc

    async def _reset_mcp_session(self):
        """MCP 세션 닫고 상태 초기화."""
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
            raise RuntimeError(
                f"No API key / client for provider '{provider}' "
                f"(model='{effective_model}'). Add the key to .env."
            )

        # Per-provider rate limiting
        min_wait = _MIN_WAIT.get(provider, 2.0)
        elapsed = time.time() - _LAST_API_CALL.get(provider, 0)
        if elapsed < min_wait:
            wait_time = min_wait - elapsed
            print(f"   ⏳ Rate limiting ({provider}): waiting {wait_time:.1f}s...")
            await asyncio.sleep(wait_time)
        _LAST_API_CALL[provider] = time.time()

        loop = asyncio.get_event_loop()

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
                # Cache the (large, mostly-static) system prompt. Repeated agent
                # calls within a run reuse the cached prefix at ~0.1x input cost.
                # Prefixes shorter than the model minimum silently skip caching.
                kwargs["system"] = [{
                    "type": "text",
                    "text": "\n\n".join(system_parts),
                    "cache_control": {"type": "ephemeral"},
                }]
            response = await loop.run_in_executor(
                None,
                lambda: client.messages.create(**kwargs),
            )
            usage = getattr(response, "usage", None)
            if usage and getattr(usage, "cache_read_input_tokens", 0):
                print(f"   💾 cache hit: {usage.cache_read_input_tokens} tok "
                      f"({effective_model})")
            return response.content[0].text

        # Gemini (google-genai SDK)
        prompt = ""
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                prompt += f"[System Instructions]\n{content}\n\n"
            elif role == "user":
                prompt += f"User: {content}\n\n"
            elif role == "assistant":
                prompt += f"Assistant: {content}\n\n"
        gen_kwargs = {"model": effective_model, "contents": prompt}
        # Gemini 2.5 Flash enables "thinking" by default — unnecessary cost and
        # latency for these throughput agents. Disable it (budget=0) where the
        # SDK/model supports it; fall back to defaults otherwise.
        if "2.5" in effective_model and "flash" in effective_model:
            try:
                gen_kwargs["config"] = _gemini_genai.types.GenerateContentConfig(
                    temperature=0.3,
                    thinking_config=_gemini_genai.types.ThinkingConfig(thinking_budget=0),
                )
            except Exception:
                pass  # older SDK without ThinkingConfig — use defaults
        response = await client.aio.models.generate_content(**gen_kwargs)
        return response.text

    async def _call_global_planner(self, user_task: str) -> Dict[str, Any]:
        """
        Global Planner: parses the user query, decides single vs domain mode,
        and decomposes domain queries into subtasks.
        Returns a dict with intent fields + mode + subtasks.
        Falls back to {} on parse failure.
        """
        print("\n🌐 [Global Planner] Parsing query and deciding strategy...")

        prompt = [
            {"role": "system", "content": load_prompt("global_planner/system")},
            {"role": "user", "content": user_task},
        ]
        response = await self._call_llm(prompt, model=GLOBAL_PLANNER_MODEL)

        try:
            json_match = re.search(r"\{[\s\S]*\}", response)
            if not json_match:
                print("   ⚠️ Global Planner produced no JSON — falling back to single mode")
                return {}
            plan = json.loads(json_match.group(0))
            _verify_kr_ticker_in_subject(plan)
            subtasks = plan.get("subtasks", [])
            mode = "domain" if len(subtasks) > 1 else "single"
            print(f"   📍 Subject: {plan.get('subject', '?')}")
            print(f"   📍 Mode: {mode} | Subtasks: {len(subtasks)}")
            if subtasks:
                for st in subtasks:
                    print(f"      • {st.get('focus', '?')}  🔍 hints={st.get('search_hints', [])}")
            return plan
        except json.JSONDecodeError as e:
            print(f"   ⚠️ Global Planner JSON parse failed: {e}")
            return {}

    def _format_intent_context(self, intent: Dict[str, Any]) -> str:
        """Render extracted-intent dict as a Planner-readable fragment, or '' if empty."""
        if not intent:
            return ""
        return load_prompt(
            "intent_extractor/context",
            subject=intent.get("subject", "(unknown)"),
            key_points=intent.get("key_points", []),
            intent_class=intent.get("intent_class", "(unknown)"),
            search_keywords=intent.get("search_keywords", []),
            forecast_horizon=intent.get("forecast_horizon", 5),
            notes=intent.get("notes", ""),
        )

    async def _call_planner(self, user_task: str, tool_descriptions: str, context_examples: str, semantic_knowledge: List[str] = None, critique: Optional[Dict] = None, previous_findings: str = "", extracted_intent: Optional[Dict[str, Any]] = None, subtask_focus: str = "", subtask_context: str = "", subtask_search_hints: Optional[List[str]] = None) -> List[Dict]:
        """
        Planner LLM: Generates a free-form execution plan based on available tools and past memory.
        Returns a list of steps: [{"step": 1, "tool": "tool_name", "args": {...}, "reason": "..."}, ...]

        If `critique` is provided (from a previous Reflector verdict), the planner focuses on
        closing the identified gaps rather than repeating already-collected findings.
        """
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
            issues = critique.get("logical_issues") or []
            missing = critique.get("missing_data") or []
            suggested = critique.get("suggested_tools") or []
            prior = (previous_findings or "").strip()
            # Keep the planner's "already collected" window at least as wide as the
            # Global Reflector's (all_findings[:6000]) so it doesn't re-fetch data
            # the Reflector already judged present.
            if len(prior) > 6000:
                prior = prior[:6000] + "\n...(truncated)"
            critique_context = load_prompt(
                "planner/critique_context",
                issues=issues if issues else "none",
                missing=missing if missing else "none",
                suggested=suggested if suggested else "none (pick appropriate tools yourself)",
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
                search_hints=", ".join(hints) if hints else "(none — derive targeted query from focus/context)",
            )
        planner_prompt = [
            {"role": "system", "content": planner_system},
            {"role": "user", "content": f"Create an execution plan for: {user_task}"}
        ]

        response = await self._call_llm(planner_prompt, model=PLANNER_MODEL)

        # Parse the plan
        try:
            json_match = re.search(r'\[[\s\S]*\]', response)
            if json_match:
                plan = json.loads(json_match.group(0))
                print(f"   ✅ Plan created with {len(plan)} steps")
                return plan
        except json.JSONDecodeError as e:
            print(f"   ⚠️ Failed to parse plan: {e}")

        return []

    async def _call_executor(self, step: Dict, tool_result: str, accumulated_context: str, tips: List[Dict] = None) -> str:
        """
        Executor LLM: Interprets tool results and extracts key insights.
        Uses procedural memory tips to improve interpretation when available.
        Returns interpretation of the result.
        """
        print(f"\n🔧 [Executor] Processing step {step.get('step', '?')}: {step.get('tool', 'unknown')}")

        tips_context = ""
        if tips:
            tips_lines = []
            for t in tips:
                summary = t.get("result_summary", "")
                if summary:
                    tips_lines.append(f"- {summary[:200]}")
            if tips_lines:
                tips_context = load_prompt("executor/tips_context", tips_lines="\n".join(tips_lines))

        executor_system = load_prompt("executor/system", tips_context=tips_context)
        executor_prompt = [
            {"role": "system", "content": executor_system},
            {"role": "user", "content": f"""Step: {step.get('reason', 'Execute tool')}
Tool: {step.get('tool')}

Tool Output:
{tool_result[:2000]}

Previous context:
{accumulated_context[-1000:] if accumulated_context else 'None'}

Summarize the key findings from this tool output:"""}
        ]

        response = await self._call_llm(executor_prompt, model=EXECUTOR_MODEL)
        return response

    async def _call_news_analyst(self, tool_result: str) -> str:
        """Specialist: interprets news/sentiment tool output into a structured signal."""
        print("\n📰 [News Analyst] Interpreting news signal...")
        prompt = [
            {"role": "system", "content": load_prompt("news_analyst/system")},
            {"role": "user", "content": f"다음 뉴스/감성 데이터를 분석하세요:\n\n{tool_result[:3000]}"},
        ]
        return await self._call_llm(prompt, model=NEWS_ANALYST_MODEL)

    async def _call_technical_analyst(self, tool_result: str) -> str:
        """Specialist: interprets technical indicator tool output into a structured signal."""
        print("\n📈 [Technical Analyst] Interpreting technical signal...")
        prompt = [
            {"role": "system", "content": load_prompt("technical_analyst/system")},
            {"role": "user", "content": f"다음 기술적 지표 데이터를 분석하세요:\n\n{tool_result[:3000]}"},
        ]
        return await self._call_llm(prompt, model=TECHNICAL_ANALYST_MODEL)

    async def _call_forecast_interpreter(self, tool_result: str) -> str:
        """Specialist: explains why the forecast model produced this result."""
        print("\n🔮 [Forecast Interpreter] Explaining forecast reasoning...")
        prompt = [
            {"role": "system", "content": load_prompt("forecast_interpreter/system")},
            {"role": "user", "content": f"다음 시계열 예측 결과를 해석하세요:\n\n{tool_result[:3000]}"},
        ]
        return await self._call_llm(prompt, model=FORECAST_INTERPRETER_MODEL)

    async def _call_summarizer(self, user_task: str, all_findings: str) -> str:
        """
        Final summarization using Planner LLM.
        """
        print("\n📊 [Summarizer] Generating final summary...")
        
        summary_prompt = [
            {"role": "system", "content": load_prompt("summarizer/system")},
            {"role": "user", "content": f"""Task: {user_task}

Gathered Information:
{all_findings}

Provide your final analysis and recommendation (include Target Price, Stop-loss, and Risk/Reward):"""}
        ]
        
        response = await self._call_llm(summary_prompt, model=SUMMARIZER_MODEL, max_tokens=8192)
        return response

    async def _call_local_reflector(self, focus: str, findings: str) -> Dict[str, Any]:
        """Lightweight check: did the subtask produce usable output?"""
        print(f"\n🔎 [Local Reflector] Validating subtask: {focus}")
        prompt = [
            {"role": "system", "content": load_prompt("local_reflector/system")},
            {"role": "user", "content": f"Subtask: {focus}\n\nFindings:\n{findings[:2000]}"},
        ]
        response = await self._call_llm(prompt, model=LOCAL_REFLECTOR_MODEL)
        try:
            m = re.search(r"\{[\s\S]*\}", response)
            if m:
                result = json.loads(m.group(0))
                valid = result.get("valid", True)
                if not valid:
                    print(f"   ⚠️ Invalid: {result.get('issues', [])}")
                else:
                    print("   ✅ Valid")
                return result
        except json.JSONDecodeError:
            pass
        return {"valid": True, "issues": []}

    async def _call_global_reflector(self, user_task: str, all_findings: str) -> Dict[str, Any]:
        """Critique the combined domain findings for coverage, depth, and evidence."""
        print("\n🔍 [Global Reflector] Critiquing combined analysis...")
        prompt = [
            {"role": "system", "content": load_prompt("global_reflector/system")},
            {"role": "user", "content": f"User query: {user_task}\n\nCombined findings:\n{all_findings[:6000]}"},
        ]
        response = await self._call_llm(prompt, model=GLOBAL_REFLECTOR_MODEL, max_tokens=4096)
        try:
            m = re.search(r"\{[\s\S]*\}", response)
            if m:
                result = json.loads(m.group(0))
                approved = result.get("approved", False)
                print(f"   {'✅ Approved' if approved else '❌ Rejected'}: {result.get('critique', '')}")
                return result
        except json.JSONDecodeError:
            pass
        return {"approved": True, "critique": "parse error — defaulting to approved", "missing_coverage": [], "weak_points": []}

    async def _call_global_planner_defense(self, user_task: str, critique: Dict[str, Any], all_findings: str, tool_descriptions: str = "") -> Dict[str, Any]:
        """Global Planner defends its analysis and proposes new subtasks for valid critique points."""
        print("\n🛡️ [Global Planner] Responding to critique...")
        critique_text = (
            f"Critique: {critique.get('critique', '')}\n"
            f"Missing coverage: {critique.get('missing_coverage', [])}\n"
            f"Weak points: {critique.get('weak_points', [])}"
        )
        prompt = [
            {"role": "system", "content": load_prompt("global_planner/defense", tool_capabilities=tool_descriptions or "(no tools listed)")},
            {"role": "user", "content": f"User query: {user_task}\n\n{critique_text}\n\nCurrent findings (excerpt):\n{all_findings[:3000]}"},
        ]
        response = await self._call_llm(prompt, model=GLOBAL_PLANNER_MODEL, max_tokens=4096)
        try:
            m = re.search(r"\{[\s\S]*\}", response)
            if m:
                result = json.loads(m.group(0))
                new_subtasks = result.get("new_subtasks", [])
                print(f"   📝 Concedes: {result.get('concede', [])} | New subtasks: {len(new_subtasks)}")
                for st in new_subtasks:
                    print(f"      ↳ {st.get('focus', '?')}  🔍 hints={st.get('search_hints', [])}")
                return result
        except json.JSONDecodeError:
            pass
        return {"defense": "", "concede": [], "new_subtasks": []}

    async def _call_judge(self, user_task: str, critique: Dict[str, Any], defense: Dict[str, Any], tool_descriptions: str = "") -> Dict[str, Any]:
        """Judge decides whether Planner's defense is sufficient or Reflector's critique stands."""
        print("\n⚖️ [Judge] Evaluating debate...")
        debate_text = (
            f"CRITIC says:\n{critique.get('critique', '')}\n"
            f"Missing: {critique.get('missing_coverage', [])}\n"
            f"Weak: {critique.get('weak_points', [])}\n\n"
            f"PLANNER responds:\n{defense.get('defense', '')}\n"
            f"Concedes: {defense.get('concede', [])}\n"
            f"Proposes new subtasks: {[st.get('focus') for st in defense.get('new_subtasks', [])]}"
        )
        prompt = [
            {"role": "system", "content": load_prompt("judge/system", tool_capabilities=tool_descriptions or "(no tools listed)")},
            {"role": "user", "content": f"User query: {user_task}\n\n{debate_text}"},
        ]
        response = await self._call_llm(prompt, model=JUDGE_MODEL, max_tokens=2048)
        try:
            m = re.search(r"\{[\s\S]*\}", response)
            if m:
                result = json.loads(m.group(0))
                verdict = result.get("verdict", "planner")
                print(f"   ⚖️ Verdict: {verdict} — {result.get('reason', '')}")
                return result
        except json.JSONDecodeError:
            pass
        return {"verdict": "planner", "reason": "parse error — defaulting to planner", "valid_critique_points": [], "invalid_critique_points": []}

    async def _run_subtask(
        self,
        subtask: Dict[str, Any],
        session,
        tool_descriptions: str,
        semaphore: asyncio.Semaphore,
        user_task: str,
        global_plan: Dict[str, Any],
        critique: Optional[Dict[str, Any]] = None,
        previous_findings: str = "",
    ) -> Dict[str, Any]:
        """Execute one subtask: Local Planner → Execute → Local Reflector (1 retry on failure).

        On refinement iterations, `critique` (adapted from the Global Reflector /
        Judge) and `previous_findings` are forwarded to the planner so it closes the
        identified gaps instead of replanning blind. None/"" on the first iteration.
        """
        async with semaphore:
            focus = subtask.get("focus", "")
            context = subtask.get("context", "")
            search_hints = subtask.get("search_hints", []) or []
            print(f"\n📌 [Subtask] Starting: {focus}")

            async def _execute_plan(plan: List[Dict]) -> str:
                findings = ""
                for step in plan:
                    tool_name = step.get("tool")
                    if not tool_name:
                        continue
                    args = step.get("args", {})
                    tips = self.procedural_memory.get_tool_tips(tool_name)
                    try:
                        print(f"      ⚡ {tool_name}")
                        result = await session.call_tool(tool_name, arguments=args)
                        tool_output = result.content[0].text
                        if tool_name in ("stock_news", "stock_news_sentiment"):
                            interpretation = await self._call_news_analyst(tool_output)
                        elif tool_name == "stock_technical":
                            interpretation = await self._call_technical_analyst(tool_output)
                        elif tool_name in ("stock_moirai_forecast", "stock_chronos_forecast"):
                            interpretation = await self._call_forecast_interpreter(tool_output)
                        else:
                            interpretation = await self._call_executor(step, tool_output, findings, tips)
                        findings += f"\n### {step.get('reason', tool_name)}\n{interpretation}\n"
                        self.procedural_memory.save_tool_execution(tool_name, args, True, interpretation)
                    except Exception as e:
                        print(f"      ⚠️ {tool_name} failed: {e}")
                        findings += f"\n### {step.get('reason', tool_name)}: Failed - {e}\n"
                        self.procedural_memory.save_tool_execution(tool_name, args, False, str(e))
                return findings

            plan = await self._call_planner(
                user_task, tool_descriptions, "",
                extracted_intent=global_plan,
                subtask_focus=focus,
                subtask_context=context,
                subtask_search_hints=search_hints,
                critique=critique,
                previous_findings=previous_findings,
            )
            findings = await _execute_plan(plan)

            local_check = await self._call_local_reflector(focus, findings)
            if not local_check.get("valid", True):
                print(f"   🔁 Retrying subtask: {focus}")
                plan = await self._call_planner(
                    user_task, tool_descriptions, "",
                    extracted_intent=global_plan,
                    subtask_focus=focus,
                    subtask_context=context,
                    subtask_search_hints=search_hints,
                    critique=critique,
                    previous_findings=previous_findings,
                )
                findings = await _execute_plan(plan)

            return {"focus": focus, "findings": findings}

    async def _compress_if_needed(self):
        """Background task: compress semantic memory when week/month/year rolls over."""
        from datetime import datetime
        from database import get_setting, set_setting

        now = datetime.now()
        iso = now.isocalendar()
        current_week  = f"{iso[0]}-W{iso[1]:02d}"
        current_month = f"{now.year}-{now.month:02d}"
        current_year  = str(now.year)

        async def _call_compressor(messages):
            return await self._call_llm(messages, model=MEMORY_COMPRESSOR_MODEL)

        for level, setting_key, current_key in [
            ('weekly',  'last_weekly_compression',  current_week),
            ('monthly', 'last_monthly_compression', current_month),
            ('yearly',  'last_yearly_compression',  current_year),
        ]:
            last = get_setting(setting_key)
            if not last:
                set_setting(setting_key, current_key)
                continue
            if last != current_key:
                prev = _prev_period_key(level, current_key)
                try:
                    count = await self.semantic_memory.compress_period(level, prev, _call_compressor)
                    if count > 0:
                        print(f"🗜️ [Memory] {level.capitalize()} compression done: {prev} ({count} entries)")
                except Exception as e:
                    print(f"⚠️ [Memory] {level} compression failed ({prev}): {e}")
                set_setting(setting_key, current_key)

    async def _run_flow(
        self,
        user_task: str,
        global_plan: Dict[str, Any],
        session,
        tool_descriptions: str,
        context_examples: str,
        semantic_knowledge: List[str],
    ) -> str:
        """Fan-out domain analysis: parallel subtasks → Global Reflector → Judge debate loop."""
        semaphore = asyncio.Semaphore(3)
        subtasks = global_plan.get("subtasks", [])
        # Accumulate findings across iterations keyed by subtask focus. Later iters
        # run only the gap-filling subtasks the Defense proposes; prior coverage is
        # carried forward (reused), not discarded — so the Reflector always sees the
        # full picture and each iter only fills what's missing instead of replacing
        # everything with the latest narrow slice.
        findings_by_focus: Dict[str, str] = {}
        all_findings = ""  # defined even if MAX_GLOBAL_ITER == 0 (loop never runs)
        pending_critique: Optional[Dict[str, Any]] = None  # Reflector/Judge feedback for next iter
        prior_findings = ""                                # accumulated findings handed to next iter

        for global_iter in range(MAX_GLOBAL_ITER):
            print(f"\n🌐 [Domain] Global iteration {global_iter + 1}/{MAX_GLOBAL_ITER} — {len(subtasks)} subtasks")

            results = await asyncio.gather(*[
                self._run_subtask(st, session, tool_descriptions, semaphore, user_task, global_plan,
                                  critique=pending_critique, previous_findings=prior_findings)
                for st in subtasks
            ])

            # Merge this iter's results: new focuses are added, repeated focuses
            # refreshed. Focuses not re-run this iter keep their prior findings.
            for r in results:
                findings_by_focus[r["focus"]] = r["findings"]

            all_findings = "\n\n".join(
                f"## [{focus}]\n{findings}" for focus, findings in findings_by_focus.items()
            )

            global_critique = await self._call_global_reflector(user_task, all_findings)

            if global_critique.get("approved"):
                print("   ✅ Global Reflector approved — proceeding to summary")
                break

            if global_iter >= MAX_GLOBAL_ITER - 1:
                print("   ⚠️ Max global iterations reached — using current findings")
                break

            defense = await self._call_global_planner_defense(user_task, global_critique, all_findings, tool_descriptions)
            judge_verdict = await self._call_judge(user_task, global_critique, defense, tool_descriptions)

            if judge_verdict.get("verdict") == "planner":
                print("   ⚖️ Judge: Planner wins — proceeding to summary")
                break

            new_subtasks = defense.get("new_subtasks", [])
            if not new_subtasks:
                print("   ⚠️ Reflector wins but no new subtasks proposed — proceeding")
                break

            subtasks = new_subtasks
            # Schema-bridge the global debate outcome into the planner's critique
            # shape so the next iter's subtask planners get an explicit gap brief.
            # Feed only Judge-upheld points; fall back to the Reflector's raw
            # missing_coverage if the Judge supplied none.
            valid_points = judge_verdict.get("valid_critique_points") or global_critique.get("missing_coverage", [])
            pending_critique = {
                "logical_issues": global_critique.get("weak_points", []),
                "missing_data": valid_points,
                "suggested_tools": [],
            }
            prior_findings = all_findings
            print(f"   🔁 Reflector wins — {len(subtasks)} new subtasks queued | "
                  f"critique→planner: {len(valid_points)} gaps")

        return await self._call_summarizer(user_task, all_findings)


    async def run_for_web(self, user_task: str) -> str:
        """
        Web-friendly version using dual-LLM architecture (Memento paper).
        Planner → Executor flow with separate LLM roles.
        """
        saved_result = ""
        
        # 1. Memory Retrieval (Episodic + Semantic)
        trajectories = self.memory.retrieve_similar(user_task)
        context_examples = ""
        if trajectories:
            context_examples = "Here are some past successful plans for similar tasks:\n"
            for i, traj in enumerate(trajectories):
                lessons_str = ""
                if traj.get("lessons"):
                    lessons_str = f"\nLessons: {'; '.join(traj['lessons'])}"
                context_examples += f"--- Example {i+1} (score={traj.get('score', '?')}) ---\nTask: {traj['task']}\nPlan: {traj['plan']}\nResult: {traj['result']}{lessons_str}\n------------------\n"

        semantic_knowledge = self.semantic_memory.retrieve_relevant(user_task)
        if semantic_knowledge:
            print(f"🧠 Retrieved {len(semantic_knowledge)} generalized lessons from Semantic Memory")

        # 2. Memory compression (fire-and-forget background task)
        asyncio.create_task(self._compress_if_needed())

        # 3. MCP 세션 획득 (싱글톤 — Moirai 콜드 스타트 최초 1회)
        try:
            session, tool_descriptions = await self._ensure_mcp_session()
        except Exception as e:
            return f"MCP 서버 시작 실패: {e}"

        try:
            # 4. GLOBAL PLANNER — parses intent and decides single vs domain mode
            global_plan = await self._call_global_planner(user_task)

            # 5. Fan-out flow: 1 subtask for single queries, N for domain
            saved_result = await self._run_flow(
                user_task, global_plan, session, tool_descriptions,
                context_examples, semantic_knowledge,
            )
            self.memory.save_trajectory(user_task, "", saved_result, 0.8, [])
            return saved_result

        except asyncio.CancelledError:
            # wait_for 타임아웃이나 외부 취소 — 부분 결과가 있으면 반환, 없으면 재raise
            print("\n⚠️ [run_for_web] Task cancelled")
            if saved_result:
                return saved_result
            raise
        except BaseException as e:
            # Unwrap ExceptionGroup (anyio/MCP TaskGroups wrap inner errors) so the
            # real cause shows up instead of the generic "unhandled errors in a TaskGroup".
            import traceback

            def _collect(exc, out):
                sub = getattr(exc, "exceptions", None)
                if sub:
                    for s in sub:
                        _collect(s, out)
                else:
                    out.append(exc)

            leaves = []
            _collect(e, leaves)

            print("\n❌ [run_for_web] Exception detail:")
            for i, leaf in enumerate(leaves, 1):
                print(f"  [{i}] {type(leaf).__name__}: {leaf}")
                traceback.print_exception(type(leaf), leaf, leaf.__traceback__)

            if saved_result:
                return saved_result
            first = leaves[0] if leaves else e
            return f"오류가 발생했습니다: {type(first).__name__}: {first}"

if __name__ == "__main__":
    agent = MementoAgent()
    try:
        import sys
        task = "Find the latest news about AI"
        if len(sys.argv) > 1:
            task = " ".join(sys.argv[1:])
        
        asyncio.run(agent.run_for_web(task))
    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
