import asyncio
import os
import sys
import json
from database import get_setting
import re
import time
from typing import List, Dict, Any, Optional, Tuple
from dotenv import load_dotenv

# Load .env file from project root
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Handle both relative and absolute imports
try:
    from .memory_store import MemoryStore, ProceduralMemory, SemanticMemory
    from .driver_memory import DriverMemory
except ImportError:
    from memory_store import MemoryStore, ProceduralMemory, SemanticMemory
    from driver_memory import DriverMemory

# Provider selection: "gemini" (default, free), "openai", or "groq"
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "gemini").lower()
MOCK_MODE = False
LAST_API_CALL = 0  # Rate limiting

# Check API keys and initialize
if LLM_PROVIDER == "gemini":
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not GEMINI_API_KEY:
        MOCK_MODE = True
    else:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
elif LLM_PROVIDER == "openai":
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
    if not OPENAI_API_KEY:
        MOCK_MODE = True
    else:
        from openai import OpenAI
elif LLM_PROVIDER == "groq":
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
    if not GROQ_API_KEY:
        MOCK_MODE = True
    else:
        from groq import Groq

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
            print("[Agent] Using OpenAI GPT-4o.")
            self.client = OpenAI()
        elif LLM_PROVIDER == "groq":
            print("[Agent] Using Groq Llama 3.3 70B (fast inference).")
            self.client = Groq(api_key=GROQ_API_KEY)
        else:
            print("[Agent] Using Gemini 2.0 Flash (free tier).")
            self.model = genai.GenerativeModel('gemini-2.0-flash')

    def _call_llm(self, messages):
        global LAST_API_CALL
        if MOCK_MODE:
            return self.llm.chat(messages)
        
        # Rate limiting: Groq is fast, less limiting needed
        if LLM_PROVIDER == "groq":
            min_wait = 1  # Groq is fast
        else:
            min_wait = 7  # Gemini/OpenAI need more spacing
        
        elapsed = time.time() - LAST_API_CALL
        if elapsed < min_wait:
            wait_time = min_wait - elapsed
            print(f"   ⏳ Rate limiting: waiting {wait_time:.1f}s...")
            time.sleep(wait_time)
        LAST_API_CALL = time.time()
        
        if LLM_PROVIDER == "openai":
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                temperature=0.7
            )
            return response.choices[0].message.content
        elif LLM_PROVIDER == "groq":
            response = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                temperature=0.7,
                max_tokens=4096
            )
            return response.choices[0].message.content
        else:
            # Gemini format
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
            
            response = self.model.generate_content(prompt)
            return response.text

    def _call_planner(self, user_task: str, tool_descriptions: str, context_examples: str, driver_info: str = "", semantic_knowledge: List[str] = None, critique: Optional[Dict] = None, previous_findings: str = "") -> List[Dict]:
        """
        Planner LLM: Generates a free-form execution plan based on available tools and past memory.
        Returns a list of steps: [{"step": 1, "tool": "tool_name", "args": {...}, "reason": "..."}, ...]

        If `critique` is provided (from a previous Reflector verdict), the planner focuses on
        closing the identified gaps rather than repeating already-collected findings.
        """
        print("\n📋 [Planner] Generating execution plan...")

        memory_context = ""
        if context_examples:
            memory_context = f"""
## Past Successful Plans (Retrieved from Memory)
These are real examples of plans that worked well for similar tasks.
Use them as inspiration — adapt freely to the current request, don't copy blindly.
{context_examples}"""

        driver_context = ""
        if driver_info:
            driver_context = f"""
## Historical Driver Keywords (from Driver Memory)
{driver_info}"""

        semantic_context = ""
        if semantic_knowledge:
            lessons_text = "\n".join(f"- {lesson}" for lesson in semantic_knowledge)
            semantic_context = f"""
## Generalized Knowledge (from Semantic Memory)
These lessons were learned across all past analyses — apply them when relevant:
{lessons_text}"""

        critique_context = ""
        if critique:
            issues = critique.get("logical_issues") or []
            missing = critique.get("missing_data") or []
            suggested = critique.get("suggested_tools") or []
            prior = (previous_findings or "").strip()
            if len(prior) > 1800:
                prior = prior[:1800] + "\n...(truncated)"
            critique_context = f"""
## Refinement Brief (IMPORTANT — this is a follow-up iteration)
The previous analysis was rejected by the Reflector. Your job is to CLOSE THE GAPS — not redo everything.

- Logical inconsistencies to resolve: {issues if issues else 'none'}
- Missing data to collect: {missing if missing else 'none'}
- Suggested tools to fill gaps: {suggested if suggested else 'none (pick appropriate tools yourself)'}

Already collected findings (DO NOT re-fetch these, build on them):
{prior if prior else 'none'}

Produce a FOCUSED plan with only the steps needed to address the gaps above.
Prefer 1-3 steps. If no new tool call is needed and the issue is purely logical,
return an empty array [] and the Summarizer will re-reason over existing data."""

        planner_prompt = [
            {"role": "system", "content": f"""You are a Planning Agent for stock and market analysis.

Given a user's request, create the best execution plan using the available tools.
You decide which tools to call, in what order, and how many steps are needed.

## Available Tools
{tool_descriptions}
{memory_context}
{driver_context}
{semantic_context}
{critique_context}

## Guidelines
- Understand the user's intent first, then choose the most relevant tools
- Not every query requires a specific stock ticker — use tools creatively for broad market questions
- Fewer well-chosen steps are better than many redundant ones
- When past examples exist in memory, learn from their structure but adapt to the current request
- **Event extraction** — If the user mentions a specific event (CEO change/resignation, earnings release, lawsuit, regulatory issue, product launch, M&A, layoffs, supply deal, etc.), you MUST pass that event keyword as the `query` argument to `stock_news` in addition to `ticker`. Example: user says "요즘 대표가 사퇴했다는데" → call `stock_news` with `{{"ticker": "NFLX", "query": "CEO resignation"}}`. Without `query`, only a generic news feed is returned and the specific event may be missed.

## Output Format
Output ONLY a valid JSON array of steps. Each step must have:
- "step": step number (1, 2, 3...)
- "tool": exact tool name from Available Tools above
- "args": arguments as a JSON object
- "reason": why this step serves the current request

Output ONLY the JSON array, no other text."""},
            {"role": "user", "content": f"Create an execution plan for: {user_task}"}
        ]

        response = self._call_llm(planner_prompt)

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

    def _call_executor(self, step: Dict, tool_result: str, accumulated_context: str, tips: List[Dict] = None) -> str:
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
                tips_context = f"""
## Procedural Memory: Past Successful Results for this Tool
Learn from these previous interpretations to improve yours:
{chr(10).join(tips_lines)}
"""

        executor_prompt = [
            {"role": "system", "content": f"""You are an Execution Agent for stock analysis.
Your job is to interpret tool results and extract key insights.
{tips_context}
Be concise. Focus on:
- Key numbers and metrics
- Important signals (bullish/bearish)
- Notable trends or news

Output a brief summary (2-3 sentences max)."""},
            {"role": "user", "content": f"""Step: {step.get('reason', 'Execute tool')}
Tool: {step.get('tool')}

Tool Output:
{tool_result[:2000]}

Previous context:
{accumulated_context[-1000:] if accumulated_context else 'None'}

Summarize the key findings from this tool output:"""}
        ]

        response = self._call_llm(executor_prompt)
        return response

    def _call_summarizer(self, user_task: str, all_findings: str) -> str:
        """
        Final summarization using Planner LLM.
        """
        print("\n📊 [Planner] Generating final summary...")
        
        summary_prompt = [
            {"role": "system", "content": """You are a Stock Expert AI providing final analysis.
Based on all the gathered information, provide a comprehensive summary with:
1. Current situation (price, trend)
2. Technical analysis summary
3. Fundamental factors
4. News sentiment
5. **Risk Management** (IMPORTANT - always include if data available):
   - 🎯 Target Price: [price] ([+X.X%])
   - 🛑 Stop-loss: [price] ([-X.X%])
   - ⚖️ Risk/Reward Ratio: [X.X]:1 (Entry Rating: [EXCELLENT/GOOD/FAIR/POOR])
6. Clear recommendation (BUY/HOLD/SELL) with reasoning

Be professional but concise. ALWAYS include Target Price, Stop-loss, and Risk/Reward if the data is available in the findings."""},
            {"role": "user", "content": f"""Task: {user_task}

Gathered Information:
{all_findings}

Provide your final analysis and recommendation (include Target Price, Stop-loss, and Risk/Reward):"""}
        ]
        
        response = self._call_llm(summary_prompt)
        return response

    def _extract_reflection_feedback(self, user_task: str, plan_text: str, final_analysis: str) -> dict:
        """
        Extract structured feedback from this analysis cycle for memory update.
        Returns {"score": float, "lessons": [str]}
        """
        print("\n💾 [Reflector] Extracting lessons for memory update...")

        feedback_prompt = [
            {"role": "system", "content": """You are a meta-learning agent. Analyze a completed stock analysis task and extract lessons for future improvement.

Output ONLY a valid JSON object with this structure:
{
  "score": <float 0.0-1.0 representing analysis quality>,
  "lessons": [<up to 3 concise lessons learned from this task>]
}

Scoring guide:
- 1.0: Complete data, clear recommendation, well-supported conclusion
- 0.7: Mostly complete, minor gaps
- 0.4: Significant data missing or contradictory signals unresolved
- 0.1: Failed or very incomplete

Lessons should be specific and actionable for a future Planner, e.g.:
- "For semiconductor stocks, searching '[company] HBM 수율' yields more relevant news than generic queries"
- "When RSI and MACD diverge, recommend HOLD rather than BUY/SELL"
- "Market-wide queries work better with stock_news than stock_price for index tickers" """},
            {"role": "user", "content": f"""Task: {user_task}

Plan executed:
{plan_text}

Final analysis produced:
{final_analysis[:1500]}

Extract score and lessons:"""}
        ]

        try:
            response = self._call_llm(feedback_prompt)
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

    def _call_reflector(self, user_task: str, analysis: str, plan_text: str = "", peer_context: dict = None, tech_data: dict = None, available_tools: str = "") -> Tuple[str, dict, dict]:
        """
        Self-Reflection: Reviews the analysis for logical consistency and completeness.
        Uses Reference Proxy verification when available.
        Returns (final_analysis, feedback_dict, verdict_dict).

        verdict_dict schema:
          {
            "approved": bool,              # True if analysis is acceptable → stop refinement loop
            "confidence": "High|Medium|Low",
            "logical_issues": [str, ...],  # inconsistencies the planner should resolve
            "missing_data": [str, ...],    # data gaps (e.g., "news_sentiment")
            "suggested_tools": [str, ...], # tool names to fill gaps
            "revised_analysis": Optional[str]  # minor wording rewrite; used only when approved=True
          }
        """
        print("\n🔍 [Reflector] Self-reflection in progress...")

        # Get settings
        risk_tolerance = get_setting("risk_tolerance", "Medium")

        # Reference Proxy Verification
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

        print(f"   📋 Confidence Level: {confidence_level}")

        tools_hint = ""
        if available_tools:
            tools_hint = f"\n\n## Available tools (use exact names in suggested_tools):\n{available_tools}"

        reflection_prompt = [
            {"role": "system", "content": f"""You are a Critical Review Agent for stock analysis.

Review the analysis along these axes:

1. **Logical Consistency** — do indicators match the recommendation?
   - e.g., RSI < 30 (oversold) should NOT lead to SELL
   - e.g., Bearish trend + Bearish technicals should NOT support BUY without strong justification
2. **Completeness** — price/trend, 2-3 technical indicators, news sentiment, risk warnings, clear BUY/HOLD/SELL
3. **Reference Proxy Verification**
   - Preliminary Confidence: {confidence_level}
   - Notes: {'; '.join(verification_notes) if verification_notes else 'N/A'}
   - If signals are divergent, downgrade confidence and require explicit warning
4. **Confidence Calibration** — no overconfidence with limited data; acknowledge uncertainty
5. **Risk Tolerance Fit** — user's tolerance is **{risk_tolerance}**; emphasize stop-loss if Medium or lower
{tools_hint}

## Decision rule
- If the analysis has **missing data** or **logical contradictions that require new tool calls** → set approved=false
  and list the gaps in missing_data / suggested_tools so the Planner can fix them in the next iteration.
- If only **minor wording** is off (data is complete, logic is sound) → set approved=true and put the
  lightly-revised text in revised_analysis.
- If everything is fine as-is → approved=true, revised_analysis=null.

## Output format
Return ONLY a valid JSON object, no other text, no markdown fences:
{{
  "approved": true,
  "confidence": "High",
  "logical_issues": [],
  "missing_data": [],
  "suggested_tools": [],
  "revised_analysis": null
}}"""},
            {"role": "user", "content": f"""Task: {user_task}

Analysis to review:
{analysis}

Return the JSON verdict object now:"""}
        ]

        response = self._call_llm(reflection_prompt)

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
            final_analysis = analysis  # keep current text; Planner will refine in next iteration

        # Phase 2: Extract feedback for memory update (score + lessons)
        feedback = self._extract_reflection_feedback(user_task, plan_text, final_analysis)

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
            match = re.search(r'\{[\s\S]*\}', response)
            if not match:
                print("   ⚠️ Reflector output had no JSON object — defaulting to approved")
                return default_approved
            verdict = json.loads(match.group(0))
            verdict.setdefault("approved", True)
            verdict.setdefault("confidence", "Medium")
            verdict.setdefault("logical_issues", [])
            verdict.setdefault("missing_data", [])
            verdict.setdefault("suggested_tools", [])
            verdict.setdefault("revised_analysis", None)
            return verdict
        except json.JSONDecodeError as e:
            print(f"   ⚠️ Reflector JSON parse failed ({e}) — defaulting to approved")
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

                # 3. Planning & Execution Loop
                history = [
                    {"role": "system", "content": f"""You are a Professional Stock Expert AI Assistant.

## Your Expertise
- 📊 Technical Analysis: RSI, MACD, Bollinger Bands, Moving Averages
- 📈 Fundamental Analysis: PER, PBR, ROE, EPS, Financial Statements
- 🤖 AI-Powered Prediction: Chronos time-series + FinBERT sentiment
- 📰 Real-time News & Market Sentiment Analysis

## User Configuration
- **Risk Tolerance**: {get_setting("risk_tolerance", "Medium")}
- **Default Market**: {get_setting("default_market", "KR")}

## Your Task
{user_task}

## Past Successful Analyses (for reference)
{context_examples}

## Available Tools
{tool_descriptions}

## Guidelines
1. **Always verify data** - Use real-time data from tools before giving advice
2. **Be comprehensive** - Consider both technical and fundamental factors
3. **Risk disclosure** - Always mention investment risks
4. **Clear recommendations** - Give actionable insights (BUY/SELL/HOLD)

## Tool Calling Format
To call a tool, output ONLY a JSON block:
{{"tool": "tool_name", "arguments": {{"arg_name": "value"}}}}

## Completion
When you have completed the analysis, output:
DONE: [Your comprehensive stock analysis summary with recommendation]

"""},
                    {"role": "user", "content": f"Please execute the task: {user_task}"}
                ]

                plan_text = ""
                final_result = ""
                
                print("\n🤔 Thinking...")
                for _ in range(10):
                    content = self._call_llm(history)
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

                    # 3. PLAN → EXECUTE → SUMMARIZE → REFLECT loop (iterative refinement)
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
                        plan = self._call_planner(
                            user_task, tool_descriptions, context_examples,
                            semantic_knowledge=semantic_knowledge,
                            critique=critique,
                            previous_findings=all_findings,
                        )

                        if not plan:
                            if iteration == 0:
                                saved_result = "계획 생성에 실패했습니다. 다시 시도해주세요."
                                return saved_result
                            # Refinement iteration returned []: Planner decided no new tool call is needed.
                            # Skip the executor and let the Summarizer/Reflector re-reason over existing findings.
                            print("   ℹ️ No new plan steps — re-summarizing with existing findings")
                        else:
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
                                                    {"role": "system", "content": "You are a financial analyst. Return ONLY a JSON array of competitor tickers."},
                                                    {"role": "user", "content": f"List 2-3 key industry competitors for {ticker}. Return ONLY a JSON array like [\"TICKER1\", \"TICKER2\"]. For Korean stocks, use .KS suffix."}
                                                ]
                                                llm_response = self._call_llm(fallback_prompt)

                                                try:
                                                    ticker_match = re.search(r'\[.*?\]', llm_response)
                                                    if ticker_match:
                                                        competitor_tickers = json.loads(ticker_match.group(0))
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
                                            print(f"   📈 Technical data captured: {tech_data.get('recommendation', 'N/A')}")
                                        except:
                                            pass

                                    # Executor interprets the result (with procedural memory tips)
                                    interpretation = self._call_executor(step, tool_output, all_findings, tips)
                                    all_findings += f"\n### [iter {iteration + 1}] Step {step.get('step')}: {step.get('reason', tool_name)}\n{interpretation}\n"

                                    # Save to procedural memory
                                    self.procedural_memory.save_tool_execution(
                                        tool_name, args, True, interpretation
                                    )

                                except Exception as e:
                                    print(f"   ⚠️ Step failed: {e}")
                                    all_findings += f"\n### [iter {iteration + 1}] Step {step.get('step')}: Failed - {str(e)}\n"
                                    # Save failure to procedural memory
                                    self.procedural_memory.save_tool_execution(
                                        tool_name, args, False, str(e)
                                    )

                        # SUMMARIZER: regenerate the analysis from the latest cumulative findings
                        final_result = self._call_summarizer(user_task, all_findings)

                        # REFLECTOR: structured verdict
                        final_result, feedback, verdict = self._call_reflector(
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
