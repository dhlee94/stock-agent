import asyncio
import os
import json
import re
import time
from typing import List, Dict, Any
from dotenv import load_dotenv

# Load .env file from project root
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Handle both relative and absolute imports
try:
    from .memory_store import MemoryStore, ProceduralMemory
    from .driver_memory import DriverMemory
except ImportError:
    from memory_store import MemoryStore, ProceduralMemory
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

    def _call_planner(self, user_task: str, tool_descriptions: str, context_examples: str, driver_info: str = "") -> List[Dict]:
        """
        Planner LLM: Generates a structured execution plan.
        Returns a list of steps: [{"step": 1, "tool": "tool_name", "args": {...}, "reason": "..."}, ...]
        """
        print("\n📋 [Planner] Generating execution plan...")
        
        # Build driver context
        driver_context = ""
        if driver_info:
            driver_context = f"""
## 📍 Historical Driver Keywords (IMPORTANT)
{driver_info}
Use these keywords for TARGETED news searches instead of generic queries.
Example: Instead of "삼성전자 뉴스", search "삼성전자 HBM" or "삼성전자 파업".
"""
        
        planner_prompt = [
            {"role": "system", "content": f"""You are a Planning Agent for stock analysis.
Your job is to create a detailed execution plan for the given task.

## CRITICAL WORKFLOW
1. **Identify Entity**: Extract the stock ticker from user's request
2. **Check Driver Memory**: If analyzing a stock, ALWAYS call `analyze_drivers` first to get key impact factors
3. **Strategic Planning**: Use the driver keywords for TARGETED news/research queries
4. **[REQUIRED] Peer Group Analysis**: MUST call `analyze_peers` for STL Trend correlation analysis with sector peers
5. **[REQUIRED] Risk Management**: ALWAYS call `calculate_risk` to get Target Price, Stop-loss, and Risk/Reward ratio
6. **Synthesis**: Adjust outlook based on Reference Proxy's momentum if correlation > 0.7

⚠️ MANDATORY STEPS: You MUST include BOTH `analyze_peers` AND `calculate_risk` in EVERY plan.
{driver_context}
## Available Tools
{tool_descriptions}

## Past Successful Plans (for reference)
{context_examples}

## Output Format
You MUST output a valid JSON array of steps. Each step should have:
- "step": step number (1, 2, 3...)
- "tool": exact tool name to call
- "args": arguments for the tool as a JSON object
- "reason": brief explanation of why this step is needed

IMPORTANT: For stock_news, use SPECIFIC keyword queries based on driver analysis.
BAD: {{"tool": "stock_news", "args": {{"query": "삼성전자"}}}}
GOOD: {{"tool": "stock_news", "args": {{"query": "삼성전자 HBM 현황"}}}}

Example output:
[
  {{"step": 1, "tool": "analyze_drivers", "args": {{"ticker": "005930.KS", "name": "삼성전자"}}, "reason": "Identify key price drivers"}},
  {{"step": 2, "tool": "stock_price", "args": {{"ticker": "005930.KS", "market": "KR"}}, "reason": "Get current price"}},
  {{"step": 3, "tool": "stock_technical", "args": {{"ticker": "005930.KS"}}, "reason": "Technical analysis for support/resistance"}},
  {{"step": 4, "tool": "stock_news", "args": {{"query": "삼성전자 HBM"}}, "reason": "Check HBM news (top driver)"}},
  {{"step": 5, "tool": "analyze_peers", "args": {{"ticker": "005930.KS"}}, "reason": "Find correlated stocks via news entity mining"}},
  {{"step": 6, "tool": "calculate_risk", "args": {{"ticker": "005930.KS", "market": "KR"}}, "reason": "Calculate Target Price and Stop-loss"}}
]

Output ONLY the JSON array, no other text."""},
            {"role": "user", "content": f"Create an execution plan for: {user_task}"}
        ]
        
        response = self._call_llm(planner_prompt)
        
        # Parse the plan
        try:
            # Try to extract JSON from response
            json_match = re.search(r'\[[\s\S]*\]', response)
            if json_match:
                plan = json.loads(json_match.group(0))
                print(f"   ✅ Plan created with {len(plan)} steps")
                return plan
        except json.JSONDecodeError as e:
            print(f"   ⚠️ Failed to parse plan: {e}")
        
        # Fallback: return empty plan
        return []

    def _call_executor(self, step: Dict, tool_result: str, accumulated_context: str) -> str:
        """
        Executor LLM: Interprets tool results and decides next action.
        Returns interpretation of the result.
        """
        print(f"\n🔧 [Executor] Processing step {step.get('step', '?')}: {step.get('tool', 'unknown')}")
        
        executor_prompt = [
            {"role": "system", "content": """You are an Execution Agent for stock analysis.
Your job is to interpret tool results and extract key insights.

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

    def _call_reflector(self, user_task: str, analysis: str, peer_context: dict = None, tech_data: dict = None) -> str:
        """
        Self-Reflection: Reviews the analysis for logical consistency and completeness.
        Uses Reference Proxy verification when available.
        Returns improved analysis if issues found, otherwise returns original.
        """
        print("\n🔍 [Reflector] Self-reflection in progress...")
        
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
        
        reflection_prompt = [
            {"role": "system", "content": f"""You are a Critical Review Agent for stock analysis.
Your job is to review the analysis and check for:

1. **Logical Consistency**: Do the indicators match the recommendation?
   - Example: RSI < 30 (oversold) should NOT lead to SELL recommendation
   - Example: Positive news + Bullish technicals should support BUY

2. **Completeness**: Are key elements present?
   - Price and trend information
   - At least 2-3 technical indicators
   - Risk warnings for volatile stocks
   - Clear BUY/HOLD/SELL recommendation

3. **Reference Proxy Verification (IMPORTANT)**:
   - Confidence Level: {confidence_level}
   - Verification Notes: {'; '.join(verification_notes) if verification_notes else 'N/A'}
   
   If confidence is "Low" (divergent signals), add a WARNING about conflicting sector trends.
   If confidence is "High" (aligned), mention the strong sector alignment.

4. **Confidence Level**: Is the recommendation appropriately confident?
   - Don't be overconfident with limited data
   - Acknowledge uncertainties

If issues are found, provide a REVISED analysis.
If no issues, respond with: "APPROVED: [original analysis]"
"""},
            {"role": "user", "content": f"""Task: {user_task}

Analysis to review:
{analysis}

Review this analysis and either approve it or provide a revised version:"""}
        ]
        
        response = self._call_llm(reflection_prompt)
        
        if response.startswith("APPROVED:"):
            print("   ✅ Analysis approved without changes")
            return analysis
        else:
            print("   📝 Analysis revised after reflection")
            return response

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
            command="python3",
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
        
        # 1. Memory Retrieval
        trajectories = self.memory.retrieve_similar(user_task)
        context_examples = ""
        if trajectories:
            context_examples = "Here are some past successful plans for similar tasks:\n"
            for i, traj in enumerate(trajectories):
                context_examples += f"--- Example {i+1} ---\nTask: {traj['task']}\nPlan: {traj['plan']}\nResult: {traj['result']}\n------------------\n"

        # 2. Connect to MCP Server
        server_params = StdioServerParameters(
            command="python3",
            args=[self.server_script],
        )

        try:
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    
                    tools_response = await session.list_tools()
                    tools = tools_response.tools
                    tool_descriptions = "\n".join([f"- {t.name}: {t.description}" for t in tools])

                    # 3. PLANNER: Generate execution plan
                    plan = self._call_planner(user_task, tool_descriptions, context_examples)
                    
                    if not plan:
                        saved_result = "계획 생성에 실패했습니다. 다시 시도해주세요."
                        return saved_result
                    
                    # 4. EXECUTOR: Execute each step
                    all_findings = ""
                    plan_text = json.dumps(plan, ensure_ascii=False, indent=2)
                    peer_context = None  # Store Reference Proxy for Reflector verification
                    tech_data = None     # Store technical signal for alignment check
                    
                    for step in plan:
                        tool_name = step.get("tool")
                        args = step.get("args", {})
                        
                        if not tool_name:
                            continue
                        
                        # Get tips from procedural memory
                        tips = self.procedural_memory.get_tool_tips(tool_name)
                        if tips:
                            print(f"   💡 Found {len(tips)} past successful executions for {tool_name}")
                        
                        try:
                            # Execute tool
                            print(f"   ⚡ Executing: {tool_name}")
                            result = await session.call_tool(tool_name, arguments=args)
                            tool_output = result.content[0].text
                            
                            # Capture peer analysis result for Reflector
                            if tool_name == "analyze_peers":
                                try:
                                    peer_data = json.loads(tool_output)
                                    reference_proxy = peer_data.get("reference_proxy")
                                    peer_context = {
                                        "peers_found": peer_data.get("entity_mining", {}).get("found_peers", 0),
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
                            
                            # Executor interprets the result
                            interpretation = self._call_executor(step, tool_output, all_findings)
                            all_findings += f"\n### Step {step.get('step')}: {step.get('reason', tool_name)}\n{interpretation}\n"
                            
                            # Save to procedural memory
                            self.procedural_memory.save_tool_execution(
                                tool_name, args, True, interpretation
                            )
                            
                        except Exception as e:
                            print(f"   ⚠️ Step failed: {e}")
                            all_findings += f"\n### Step {step.get('step')}: Failed - {str(e)}\n"
                            # Save failure to procedural memory
                            self.procedural_memory.save_tool_execution(
                                tool_name, args, False, str(e)
                            )
                    
                    # 5. PLANNER (Summarizer): Generate final analysis
                    final_result = self._call_summarizer(user_task, all_findings)
                    
                    # 6. REFLECTOR: Self-reflection on the analysis
                    final_result = self._call_reflector(user_task, final_result, peer_context, tech_data)
                    
                    # Save result before leaving context
                    saved_result = final_result if final_result else "분석을 완료하지 못했습니다."
                    
                    # 7. Save to Memory
                    self.memory.save_trajectory(user_task, plan_text, final_result, 1.0)
                    
        except Exception as e:
            if saved_result:
                return saved_result
            return f"오류가 발생했습니다: {str(e)}"
        
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
