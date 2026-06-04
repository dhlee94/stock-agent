import asyncio
import os
import sys
import json
import re
import time
from typing import List, Dict, Any, Optional, Tuple

# Use centralized config
from config import (
    LLM_PROVIDER, LLM_MODEL,
    GEMINI_API_KEY, OPENAI_API_KEY, GROQ_API_KEY, ANTHROPIC_API_KEY,
    DEFAULT_MARKET, RISK_TOLERANCE, SRC_DIR,
    PLANNER_MODEL, EXECUTOR_MODEL, REFLECTOR_MODEL, SUMMARIZER_MODEL,
    INTENT_EXTRACTOR_MODEL, NEWS_ANALYST_MODEL, TECHNICAL_ANALYST_MODEL,
    FORECAST_INTERPRETER_MODEL,
)
from database import get_setting
from tools.stock.kr_listing import lookup_kr_ticker
from tools.stock.us_listing import lookup_us_ticker, is_valid_us_ticker
from tools.stock.market_utils import NAME_TO_TICKER

# Provider setup
MOCK_MODE = False
LAST_API_CALL = 0  # Rate limiting

# Initialize providers based on config
if LLM_PROVIDER == "gemini":
    if not GEMINI_API_KEY:
        MOCK_MODE = True
    else:
        from google import genai as _gemini_genai
        _gemini_client = _gemini_genai.Client(api_key=GEMINI_API_KEY)
elif LLM_PROVIDER == "openai":
    if not OPENAI_API_KEY:
        MOCK_MODE = True
    else:
        from openai import OpenAI
elif LLM_PROVIDER == "groq":
    if not GROQ_API_KEY:
        MOCK_MODE = True
    else:
        from groq import Groq
elif LLM_PROVIDER == "anthropic":
    if not ANTHROPIC_API_KEY:
        MOCK_MODE = True
    else:
        import anthropic

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Handle both relative and absolute imports
try:
    from .memory_store import MemoryStore, ProceduralMemory, SemanticMemory
    from .driver_memory import DriverMemory
    from .prompts import load_prompt
except ImportError:
    from memory_store import MemoryStore, ProceduralMemory, SemanticMemory
    from driver_memory import DriverMemory
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


class MementoAgent:
    def __init__(self):
        self.memory = MemoryStore()
        self.semantic_memory = SemanticMemory()
        self.procedural_memory = ProceduralMemory()
        self.driver_memory = DriverMemory()
        self.server_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_server.py")
        
        if MOCK_MODE:
            print(f"[Agent] Running in MOCK mode (no API key for {LLM_PROVIDER}).")
            self.llm = MockLLM()
        elif LLM_PROVIDER == "openai":
            print(f"[Agent] Using OpenAI ({LLM_MODEL}).")
            self.client = OpenAI(api_key=OPENAI_API_KEY)
        elif LLM_PROVIDER == "groq":
            print(f"[Agent] Using Groq ({LLM_MODEL}, fast inference).")
            self.client = Groq(api_key=GROQ_API_KEY)
        elif LLM_PROVIDER == "anthropic":
            print(f"[Agent] Using Anthropic ({LLM_MODEL}).")
            self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        else:
            print(f"[Agent] Using Gemini ({LLM_MODEL}).")
            self.gemini_client = _gemini_client

    async def _call_llm(self, messages, model: str = None, max_tokens: int = 4096):
        global LAST_API_CALL
        if MOCK_MODE:
            return self.llm.chat(messages)

        effective_model = model or LLM_MODEL

        # Rate limiting
        if LLM_PROVIDER == "groq":
            min_wait = 0.5
        elif LLM_PROVIDER == "anthropic":
            min_wait = 0.5
        else:
            min_wait = 2.0

        elapsed = time.time() - LAST_API_CALL
        if elapsed < min_wait:
            wait_time = min_wait - elapsed
            print(f"   ⏳ Rate limiting: waiting {wait_time:.1f}s...")
            await asyncio.sleep(wait_time)
        LAST_API_CALL = time.time()

        if LLM_PROVIDER == "openai":
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.chat.completions.create(
                    model=effective_model,
                    messages=messages,
                    temperature=0.3,
                    max_tokens=max_tokens,
                )
            )
            return response.choices[0].message.content
        elif LLM_PROVIDER == "groq":
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.chat.completions.create(
                    model=effective_model,
                    messages=messages,
                    temperature=0.3,
                    max_tokens=max_tokens,
                )
            )
            return response.choices[0].message.content
        elif LLM_PROVIDER == "anthropic":
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
                kwargs["system"] = "\n\n".join(system_parts)
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.messages.create(**kwargs),
            )
            return response.content[0].text
        else:
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
            response = await self.gemini_client.aio.models.generate_content(
                model=effective_model,
                contents=prompt,
            )
            return response.text

    async def _call_intent_extractor(self, user_task: str) -> Dict[str, Any]:
        """
        Pre-Planner stage: parse the user's natural-language query into structured key points.
        Returns a dict with keys: subject, key_points, intent_class, search_keywords, notes.
        Returns {} on parse failure (Planner will fall back to raw query only).
        """
        print("\n🎯 [Intent Extractor] Parsing user query...")

        extractor_prompt = [
            {"role": "system", "content": load_prompt("intent_extractor/system")},
            {"role": "user", "content": user_task},
        ]
        response = await self._call_llm(extractor_prompt, model=INTENT_EXTRACTOR_MODEL)

        try:
            json_match = re.search(r"\{[\s\S]*\}", response)
            if not json_match:
                print("   ⚠️ Extractor produced no JSON — falling back")
                return {}
            intent = json.loads(json_match.group(0))
            _verify_kr_ticker_in_subject(intent)
            print(f"   📍 Subject: {intent.get('subject', '?')}")
            print(f"   📍 Key points: {intent.get('key_points', [])}")
            print(f"   📍 Intent: {intent.get('intent_class', '?')}")
            kw = intent.get("search_keywords", [])
            if kw:
                print(f"   📍 Search keywords: {kw}")
            return intent
        except json.JSONDecodeError as e:
            print(f"   ⚠️ Extractor JSON parse failed: {e}")
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

    async def _call_planner(self, user_task: str, tool_descriptions: str, context_examples: str, driver_info: str = "", semantic_knowledge: List[str] = None, critique: Optional[Dict] = None, previous_findings: str = "", extracted_intent: Optional[Dict[str, Any]] = None) -> List[Dict]:
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

        driver_context = ""
        if driver_info:
            driver_context = load_prompt("planner/driver_context", driver_info=driver_info)

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
            if len(prior) > 1800:
                prior = prior[:1800] + "\n...(truncated)"
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
            driver_context=driver_context,
            semantic_context=semantic_context,
            critique_context=critique_context,
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

    async def _extract_reflection_feedback(self, user_task: str, plan_text: str, final_analysis: str) -> dict:
        """
        Extract structured feedback from this analysis cycle for memory update.
        Returns {"score": float, "lessons": [str]}
        """
        print("\n💾 [Reflector] Extracting lessons for memory update...")

        feedback_prompt = [
            {"role": "system", "content": load_prompt("reflector/feedback_extractor")},
            {"role": "user", "content": f"""Task: {user_task}

Plan executed:
{plan_text}

Final analysis produced:
{final_analysis[:1500]}

Extract score and lessons:"""}
        ]

        try:
            response = await self._call_llm(feedback_prompt, model=REFLECTOR_MODEL)
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                feedback = json.loads(json_match.group(0))
                score = float(feedback.get("score", 0.7))
                lessons = feedback.get("lessons", [])
                print(f"   📊 Score: {score:.2f} | Lessons: {len(lessons)}")
                for lesson in lessons:
                    print(f"   💡 {lesson}")
                return {"score": score, "lessons": lessons}
        except Exception as e:
            print(f"   ⚠️ Feedback extraction failed: {e}")

        return {"score": 0.7, "lessons": []}

    async def _call_reflector(self, user_task: str, analysis: str, plan_text: str = "", peer_context: dict = None, tech_data: dict = None, available_tools: str = "") -> Tuple[str, dict, dict]:
        """
        Self-Reflection: Reviews the analysis for logical consistency and completeness.
        Uses Reference Proxy verification when available.
        Returns (final_analysis, feedback_dict, verdict_dict).
        """
        print("\n🔍 [Reflector] Self-reflection in progress...")

        # (Existing logic omitted for brevity in instruction but MUST be kept in implementation)
        # ... [Reference Proxy Verification logic] ...

        risk_tolerance = get_setting("risk_tolerance", "Medium")
        confidence_level = "Medium"
        verification_notes = []

        if peer_context and peer_context.get("has_high_correlation") and peer_context.get("reference_proxy"):
            proxy = peer_context["reference_proxy"]
            proxy_name = proxy.get("name", "Unknown")
            proxy_trend = proxy.get("momentum", {}).get("trend", "unknown")
            proxy_corr = proxy.get("trend_correlation", 0)

            if tech_data:
                our_signal = tech_data.get("recommendation", "HOLD")
                proxy_bullish = proxy_trend == "bullish"
                our_bullish = our_signal in ["BUY", "STRONG_BUY"]
                our_bearish = our_signal in ["SELL", "STRONG_SELL"]

                if (proxy_bullish and our_bullish) or (not proxy_bullish and our_bearish):
                    confidence_level = "High"
                    verification_notes.append(f"✅ Signal aligned with Reference Proxy {proxy_name} ({proxy_trend})")
                elif (proxy_bullish and our_bearish) or (not proxy_bullish and our_bullish):
                    confidence_level = "Low"
                    verification_notes.append(f"⚠️ DIVERGENT: {proxy_name} is {proxy_trend} but our signal is {our_signal}")
                else:
                    verification_notes.append(f"📊 Reference: {proxy_name} ({proxy_trend}, corr={proxy_corr:.2f})")
            print(f"   🔗 Reference Proxy Verified: {proxy_name} ({proxy_trend})")
        elif peer_context:
            verification_notes.append("⚠️ No high-correlation proxy - independent analysis")
            print("   ⚠️ No Reference Proxy available")

        tools_hint = ""
        if available_tools:
            tools_hint = load_prompt("reflector/tools_hint", available_tools=available_tools)

        reflector_system = load_prompt(
            "reflector/system",
            confidence_level=confidence_level,
            verification_notes="; ".join(verification_notes) if verification_notes else "N/A",
            risk_tolerance=risk_tolerance,
            tools_hint=tools_hint,
        )
        reflection_prompt = [
            {"role": "system", "content": reflector_system},
            {"role": "user", "content": f"""Task: {user_task}

Analysis to review:
{analysis}

Return the JSON verdict object now:"""}
        ]

        response = await self._call_llm(reflection_prompt, model=REFLECTOR_MODEL, max_tokens=8192)

        verdict = self._parse_verdict(response)
        revised = verdict.get("revised_analysis")

        if verdict.get("approved"):
            if revised and isinstance(revised, str) and revised.strip():
                print("   ✅ Approved with minor wording revision")
                final_analysis = revised.strip()
            else:
                print("   ✅ Approved as-is")
                final_analysis = analysis
        else:
            issues = verdict.get("logical_issues") or []
            missing = verdict.get("missing_data") or []
            print(f"   🔁 Rejected — logical_issues={len(issues)}, missing_data={len(missing)}")
            final_analysis = analysis 

        # Phase 2: Extract feedback for memory update (score + lessons)
        feedback = await self._extract_reflection_feedback(user_task, plan_text, final_analysis)

        return final_analysis, feedback, verdict

    def _parse_verdict(self, response: str) -> dict:
        """Parse Reflector JSON output; fall back to approved=True on parse failure."""
        default_approved = {
            "approved": True,
            "confidence": "Medium",
            "logical_issues": [],
            "missing_data": [],
            "suggested_tools": [],
            "revised_analysis": None,
        }
        if not response:
            return default_approved
        try:
            # 가장 바깥쪽 { } 블록을 찾아 파싱 — revised_analysis가 길어도 대응
            match = re.search(r'\{[\s\S]*\}', response)
            if not match:
                print("   ⚠️ Reflector output had no JSON object — defaulting to approved")
                return default_approved
            raw = match.group(0)
            try:
                verdict = json.loads(raw)
            except json.JSONDecodeError:
                # revised_analysis 안의 줄바꿈·특수문자로 JSON이 깨진 경우
                # approved / confidence 만 greedy 추출해서 최소 verdict 반환
                approved_m = re.search(r'"approved"\s*:\s*(true|false)', raw, re.I)
                conf_m = re.search(r'"confidence"\s*:\s*"(\w+)"', raw)
                print("   ⚠️ Reflector JSON partially broken — extracting approved/confidence only")
                return {
                    **default_approved,
                    "approved": approved_m.group(1).lower() == "true" if approved_m else True,
                    "confidence": conf_m.group(1) if conf_m else "Medium",
                }
            verdict.setdefault("approved", True)
            verdict.setdefault("confidence", "Medium")
            verdict.setdefault("logical_issues", [])
            verdict.setdefault("missing_data", [])
            verdict.setdefault("suggested_tools", [])
            verdict.setdefault("revised_analysis", None)
            return verdict
        except Exception as e:
            print(f"   ⚠️ Reflector parse failed ({e}) — defaulting to approved")
            return default_approved

    async def run(self, user_task: str):
        print(f"\n🚀 Starting Memento Agent for Task: {user_task}")
        
        # 1. Memory Retrieval
        print("🧠 Retrieving similar trajectories...")
        trajectories = self.memory.retrieve_similar(user_task)
        context_examples = ""
        if trajectories:
            print(f"   Found {len(trajectories)} similar examples.")
            context_examples = "Here are some past successful plans for similar tasks:\n"
            for i, traj in enumerate(trajectories):
                context_examples += f"--- Example {i+1} ---\nTask: {traj['task']}\nPlan: {traj['plan']}\nResult: {traj['result']}\n------------------\n"
        else:
            print("   No similar examples found.")

        # 2. Connect to MCP Server
        server_params = StdioServerParameters(
            command=sys.executable,
            args=[self.server_script],
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                
                tools_response = await session.list_tools()
                tools = tools_response.tools
                tool_descriptions = "\n".join([f"- {t.name}: {t.description}" for t in tools])

                # 3. Intent extraction (so the single-loop LLM also gets structured key points)
                extracted_intent = await self._call_intent_extractor(user_task)
                intent_context = self._format_intent_context(extracted_intent)

                # 4. Planning & Execution Loop
                run_system = load_prompt(
                    "run/main_system",
                    risk_tolerance=get_setting("risk_tolerance", "Medium"),
                    default_market=get_setting("default_market", "KR"),
                    user_task=user_task,
                    intent_context=intent_context,
                    context_examples=context_examples,
                    tool_descriptions=tool_descriptions,
                )
                history = [
                    {"role": "system", "content": run_system},
                    {"role": "user", "content": f"Please execute the task: {user_task}"}
                ]

                plan_text = ""
                final_result = ""
                
                print("\n🤔 Thinking...")
                for _ in range(10):
                    content = await self._call_llm(history)
                    print(f"\n🤖 Agent: {content[:500]}...")
                    history.append({"role": "assistant", "content": content})
                    plan_text += content + "\n"

                    if "DONE:" in content:
                        final_result = content.split("DONE:")[1].strip()
                        break
                    
                    try:
                        json_match = re.search(r'\{[^{}]*"tool"[^{}]*\}', content, re.DOTALL)
                        if json_match:
                            tool_call = json.loads(json_match.group(0))
                            tool_name = tool_call.get("tool")
                            args = tool_call.get("arguments", {})
                            
                            if tool_name:
                                print(f"⚡ Executing tool: {tool_name} with {args}")
                                result = await session.call_tool(tool_name, arguments=args)
                                tool_output = result.content[0].text
                                print(f"   Result: {tool_output[:200]}...")
                                history.append({"role": "user", "content": f"Tool Output ({tool_name}): {tool_output}"})
                    except Exception as e:
                        print(f"   Error: {e}")
                        history.append({"role": "user", "content": f"Error: {e}"})

                # 4. Save to Memory
                self.memory.save_trajectory(user_task, plan_text, final_result, 1.0)
                print("\n✅ Task Completed & Trajectory Saved!")

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

        # 2. Connect to MCP Server
        server_params = StdioServerParameters(
            command=sys.executable,
            args=[self.server_script],
        )

        try:
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    
                    tools_response = await session.list_tools()
                    tools = tools_response.tools
                    tool_descriptions = "\n".join([f"- {t.name}: {t.description}" for t in tools])

                    # 3. INTENT EXTRACTION (once, before the loop — reused across iterations)
                    extracted_intent = await self._call_intent_extractor(user_task)

                    # 4. PLAN → EXECUTE → SUMMARIZE → REFLECT loop (iterative refinement)
                    MAX_ITER = 3
                    all_findings = ""
                    plan_text = ""
                    peer_context = None   # Reference Proxy state (kept across iterations)
                    tech_data = None      # Technical signal (kept across iterations)
                    critique = None       # Reflector verdict from previous iteration
                    final_result = ""
                    feedback = None
                    verdict = None

                    for iteration in range(MAX_ITER):
                        print(f"\n🔄 Iteration {iteration + 1}/{MAX_ITER}")

                        # PLANNER: first iteration uses full context; later iterations receive critique + prior findings
                        plan = await self._call_planner(
                            user_task, tool_descriptions, context_examples,
                            semantic_knowledge=semantic_knowledge,
                            critique=critique,
                            previous_findings=all_findings,
                            extracted_intent=extracted_intent,
                        )

                        if not plan:
                            if iteration == 0:
                                saved_result = "계획 생성에 실패했습니다. 다시 시도해주세요."
                                return saved_result
                            # Refinement iteration returned []: Planner decided no new tool call is needed.
                            # Skip the executor and let the Summarizer/Reflector re-reason over existing findings.
                            print("   ℹ️ No new plan steps — re-summarizing with existing findings")
                        else:
                            # Step 수 상한: iteration마다 최대 8 step
                            MAX_STEPS_PER_ITER = 8
                            if len(plan) > MAX_STEPS_PER_ITER:
                                print(f"   ⚠️ Plan has {len(plan)} steps — capping at {MAX_STEPS_PER_ITER}")
                                plan = plan[:MAX_STEPS_PER_ITER]

                            plan_text += f"\n--- Iteration {iteration + 1} ---\n" + json.dumps(plan, ensure_ascii=False, indent=2)

                            # EXECUTOR: run each step in this iteration's plan
                            for step in plan:
                                tool_name = step.get("tool")
                                args = step.get("args", {})

                                if not tool_name:
                                    continue

                                # Get tips from procedural memory
                                tips = self.procedural_memory.get_tool_tips(tool_name)
                                if tips:
                                    print(f"   💡 Found {len(tips)} past executions for {tool_name} — passing to Executor")

                                try:
                                    # Execute tool
                                    print(f"   ⚡ Executing: {tool_name}")
                                    result = await session.call_tool(tool_name, arguments=args)
                                    tool_output = result.content[0].text

                                    # Capture peer analysis result for Reflector
                                    if tool_name == "analyze_peers":
                                        try:
                                            peer_data = json.loads(tool_output)
                                            peers_found = peer_data.get("entity_mining", {}).get("found_peers", 0)

                                            # FALLBACK: If no peers found, use LLM to identify competitors
                                            if peers_found == 0 and not args.get("compare_with"):
                                                print(f"   ⚠️ No peers found, using LLM fallback...")
                                                ticker = args.get("ticker", "")

                                                # Ask LLM for industry competitors
                                                fallback_prompt = [
                                                    {"role": "system", "content": load_prompt("peer_fallback/system")},
                                                    {"role": "user", "content": load_prompt("peer_fallback/user", ticker=ticker)}
                                                ]
                                                llm_response = await self._call_llm(fallback_prompt)

                                                try:
                                                    obj_match = re.search(r'\{[\s\S]*?\}', llm_response)
                                                    if obj_match:
                                                        fallback_data = json.loads(obj_match.group(0))
                                                        competitor_tickers = fallback_data.get("tickers", [])
                                                        rationale = fallback_data.get("rationale", "")
                                                        if rationale:
                                                            print(f"   🤖 Peer rationale: {rationale}")
                                                    else:
                                                        competitor_tickers = []
                                                    if competitor_tickers:
                                                        print(f"   🤖 LLM identified competitors: {competitor_tickers}")

                                                        retry_result = await session.call_tool(
                                                            "analyze_peers",
                                                            arguments={"ticker": ticker, "compare_with": competitor_tickers}
                                                        )
                                                        tool_output = retry_result.content[0].text
                                                        peer_data = json.loads(tool_output)
                                                        peers_found = peer_data.get("entity_mining", {}).get("found_peers", 0)
                                                        print(f"   ✅ Retry successful: {peers_found} peers found")
                                                except Exception as e:
                                                    print(f"   ⚠️ LLM fallback failed: {e}")

                                            reference_proxy = peer_data.get("reference_proxy")
                                            peer_context = {
                                                "peers_found": peers_found,
                                                "reference_proxy": reference_proxy,
                                                "synthesis": peer_data.get("synthesis", ""),
                                                "has_high_correlation": reference_proxy is not None
                                            }
                                            print(f"   📊 Peer context captured for Reflector verification")
                                        except:
                                            pass

                                    # Capture technical signal for alignment check
                                    if tool_name == "stock_technical":
                                        try:
                                            tech_data = json.loads(tool_output)
                                            rec = tech_data.get("recommendation") or tech_data.get("status", "N/A")
                                            if tech_data.get("status") == "error":
                                                print(f"   ⚠️ Technical tool error: {tech_data.get('error', 'unknown')}")
                                            else:
                                                print(f"   📈 Technical data captured: {rec}")
                                        except:
                                            pass

                                    # Specialist agents for key signal tools; generic Executor otherwise
                                    if tool_name in ("stock_news", "stock_news_sentiment"):
                                        interpretation = await self._call_news_analyst(tool_output)
                                    elif tool_name == "stock_technical":
                                        interpretation = await self._call_technical_analyst(tool_output)
                                    elif tool_name in ("stock_moirai_forecast", "stock_chronos_forecast"):
                                        interpretation = await self._call_forecast_interpreter(tool_output)
                                    else:
                                        interpretation = await self._call_executor(step, tool_output, all_findings, tips)
                                    all_findings += f"\n### [iter {iteration + 1}] Step {step.get('step')}: {step.get('reason', tool_name)}\n{interpretation}\n"

                                    # Save to procedural memory
                                    self.procedural_memory.save_tool_execution(
                                        tool_name, args, True, interpretation
                                    )

                                except Exception as e:
                                    err_type = type(e).__name__
                                    print(f"   ⚠️ Step failed: {err_type}: {e}")
                                    all_findings += f"\n### [iter {iteration + 1}] Step {step.get('step')}: Failed - {str(e)}\n"
                                    self.procedural_memory.save_tool_execution(
                                        tool_name, args, False, str(e)
                                    )
                                    # MCP 파이프 끊김 — 더 이상 툴 호출 불가, 즉시 요약으로
                                    if "BrokenResourceError" in err_type or "BrokenPipeError" in err_type:
                                        print("   🔴 MCP pipe broken — summarizing with collected findings")
                                        if all_findings:
                                            saved_result = await self._call_summarizer(user_task, all_findings)
                                        return saved_result or "MCP 서버 연결이 끊어졌습니다. 다시 시도해주세요."

                        # SUMMARIZER: regenerate the analysis from the latest cumulative findings
                        final_result = await self._call_summarizer(user_task, all_findings)

                        # REFLECTOR: structured verdict
                        final_result, feedback, verdict = await self._call_reflector(
                            user_task, final_result, plan_text, peer_context, tech_data,
                            available_tools=tool_descriptions
                        )

                        if verdict.get("approved"):
                            print(f"   ✅ Reflector approved on iteration {iteration + 1}")
                            break

                        if iteration < MAX_ITER - 1:
                            critique = verdict
                            print(f"   🔁 Rejected — scheduling refinement iteration {iteration + 2}")
                        else:
                            print("   ⚠️ Max iterations reached — using current analysis")

                    # Save result before leaving context
                    saved_result = final_result if final_result else "분석을 완료하지 못했습니다."

                    # 7. Save to Memory with real score and lessons from Reflector
                    self.memory.save_trajectory(
                        user_task, plan_text, final_result,
                        feedback["score"], feedback["lessons"]
                    )

                    # 8. Save each lesson to Semantic Memory for cross-task generalization
                    for lesson in feedback.get("lessons", []):
                        self.semantic_memory.save_knowledge(lesson, user_task)
                    
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
        
        return saved_result

if __name__ == "__main__":
    agent = MementoAgent()
    try:
        import sys
        task = "Find the latest news about AI"
        if len(sys.argv) > 1:
            task = " ".join(sys.argv[1:])
        
        asyncio.run(agent.run(task))
    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
