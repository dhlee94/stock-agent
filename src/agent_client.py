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
from .memory_store import MemoryStore

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

Remember: 투자 결정은 본인 책임이며, 이 분석은 참고용입니다.
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
