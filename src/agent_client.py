import asyncio
import os
import json
from database import get_setting
import re
import time
from typing import List, Dict, Any
from dotenv import load_dotenv
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Load .env file from project root
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

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
    """실제 LLM API 키가 없을 때 사용하는 간단한 데모용 Mock LLM입니다."""

    def __init__(self):
        self.step = 0
    
    def chat(self, messages):
        """간단한 도구 호출 → 요약 형태의 더미 응답을 생성합니다."""
        self.step += 1
        if self.step == 1:
            # 웹 검색 도구를 호출하는 예시
            return '{"tool": "search_web", "arguments": {"query": "최신 AI 뉴스"}}'
        elif self.step == 2:
            return 'DONE: AI가 정보를 검색했습니다. 요약: AI 기술은 매우 빠르게 발전하고 있습니다.'
        return 'DONE: 작업이 완료되었습니다.'

class MementoAgent:
    def __init__(self):
        self.memory = MemoryStore()
        self.procedural_memory = ProceduralMemory()
        self.driver_memory = DriverMemory()
        self.server_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_server.py")
        
        if MOCK_MODE:
            print(f"[Agent] API 키가 없어 MOCK 모드로 실행합니다 (프로바이더: {LLM_PROVIDER}).")
            self.llm = MockLLM()
        elif LLM_PROVIDER == "openai":
            print("[Agent] OpenAI GPT-4o 모델을 사용합니다.")
            self.client = OpenAI()
        elif LLM_PROVIDER == "groq":
            print("[Agent] Groq Llama 3.3 70B (고속 추론) 모델을 사용합니다.")
            self.client = Groq(api_key=GROQ_API_KEY)
        else:
            print("[Agent] Gemini 2.0 Flash (무료 티어) 모델을 사용합니다.")
            self.model = genai.GenerativeModel('gemini-2.0-flash')

    def _call_llm(self, messages):
        global LAST_API_CALL
        if MOCK_MODE:
            return self.llm.chat(messages)
        
        # Rate limiting: Groq는 속도가 빨라 대기 시간을 짧게 유지합니다.
        if LLM_PROVIDER == "groq":
            min_wait = 1  # Groq is fast
        else:
            min_wait = 7  # Gemini/OpenAI는 호출 간 충분한 간격이 필요
        
        elapsed = time.time() - LAST_API_CALL
        if elapsed < min_wait:
            wait_time = min_wait - elapsed
            print(f"   호출 제한으로 {wait_time:.1f}초 대기합니다...")
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
        플래너 LLM: 주어진 작업에 대해 구조화된 실행 계획을 생성합니다.
        반환 형식: [{"step": 1, "tool": "tool_name", "args": {...}, "reason": "..."}, ...]
        """
        print("\n📋 [Planner] 실행 계획을 생성합니다...")
        
        # Get settings
        search_depth = int(get_setting("search_depth", "3"))

        # Build driver context
        driver_context = ""
        if driver_info:
            driver_context = f"""
## 과거 변동성 드라이버 키워드 (중요)
{driver_info}
위 키워드들을 활용하여 **구체적인** 뉴스/리포트 검색을 수행하세요.
예시: 단순히 "삼성전자 뉴스"가 아니라 "삼성전자 HBM", "삼성전자 파업"처럼 검색합니다.
"""
        
        planner_prompt = [
            {
                "role": "system",
                "content": f"""당신은 주식 분석을 위한 **플래닝 에이전트**입니다.
당신의 임무는 사용자의 요청을 달성하기 위한 **구체적이고 실행 가능한 단계별 계획**을 만드는 것입니다.
목표 계획 길이: 약 {search_depth} ~ {search_depth + 2} 단계.

## 핵심 워크플로우
1. **종목 식별**: 사용자의 요청에서 분석 대상 종목 티커를 정확히 추출합니다.
2. **Driver 메모리 확인**: 개별 종목을 분석할 때는 항상 먼저 `analyze_drivers`를 호출하여 가격에 영향을 주는 핵심 요인을 파악합니다.
3. **전략적 검색 설계**: Driver 키워드를 활용해 **타깃형 뉴스/리서치 쿼리**를 설계합니다.
4. **[필수] 검색 관점 분해**: 아래 네 가지 관점 각각에 대해 최소 1개 이상의 검색을 포함해야 합니다.
   - **내부 요인**: 실적(earnings), 신제품, R&D, 경영진/지배구조
   - **외부 요인**: 경쟁사 움직임, 업황/산업 트렌드, 공급망 이슈
   - **거시/정책**: 환율, 금리, 정부 규제·보조금
   - **수급/심리**: 외국인·기관 순매수, 애널리스트 리포트 변화, 공매도 동향
5. **[필수] Peer 그룹 분석**: 반드시 `analyze_peers`를 호출하여 섹터 내 동종/벤치마크 종목과의 STL Trend 상관관계를 확인합니다.
6. **[필수] 리스크 관리**: 항상 `calculate_risk`를 호출하여 목표가(Target Price), 손절가(Stop-loss), 손익비(Risk/Reward)를 계산합니다.
7. **통합 판단**: 상관계수 > 0.7인 Reference Proxy의 모멘텀을 참고해 최종 방향성을 조정합니다.

## Peer 분석 실패 시 Fallback (중요)
만약 `analyze_peers` 결과에서 `found_peers`가 0이면:
1. **Peer 분석을 생략하면 안 됩니다.** 반드시 대체 로직으로 진행해야 합니다.
2. LLM의 내재 지식을 활용해 '산업 대표 벤치마크' 경쟁사를 직접 식별합니다. 예:
   - 삼성전자 → SK하이닉스(000660.KS), 마이크론(MU)
   - NVDA → AMD, INTC
   - 현대차 → 기아(000270.KS), TSLA
3. 식별한 티커들을 `compare_with` 파라미터에 넣어 `analyze_peers`를 다시 호출합니다.
   예시: {{"tool": "analyze_peers", "args": {{"ticker": "005930.KS", "compare_with": ["000660.KS", "MU"]}}}}

⚠️ **반드시 지켜야 할 규칙**: 모든 계획에는 `analyze_peers`와 `calculate_risk`가 둘 다 포함되어야 합니다.
{driver_context}
## 사용 가능한 도구 목록
{tool_descriptions}

## 과거 성공 사례 (참고용)
{context_examples}

## 출력 형식 (매우 중요)
오직 **유효한 JSON 배열 하나만** 출력해야 합니다. 각 원소(단계)는 다음 필드를 포함합니다.
- "step": 단계 번호 (1, 2, 3, ...)
- "tool": 호출할 도구 이름 (정확한 문자열)
- "args": 도구 호출에 사용할 인자(JSON 객체)
- "reason": 이 단계가 필요한 이유를 설명하는 한국어 문장

### stock_news 사용 시 주의
Driver 분석 결과를 바탕으로 **구체적인 키워드 쿼리**를 사용해야 합니다.
BAD: {{"tool": "stock_news", "args": {{"query": "삼성전자"}}}}
GOOD (내부 요인): {{"tool": "stock_news", "args": {{"query": "삼성전자 HBM 수율"}}}}
GOOD (외부 요인): {{"tool": "stock_news", "args": {{"query": "SK하이닉스 캐파 증설"}}}}
GOOD (거시): {{"tool": "stock_news", "args": {{"query": "반도체 수출 관세 영향"}}}}
GOOD (수급/심리): {{"tool": "stock_news", "args": {{"query": "삼성전자 외국인 순매수 추이"}}}}

### analyze_peers 사용 시 규칙
- 사용자가 "SK랑 비교해서", "AMD와 비교"처럼 말한 경우 → 해당 회사를 인식하여 `compare_with`에 포함합니다.
- "SK하이닉스", "SK" → "000660.KS"
- "AMD" → "AMD"
- 사용자가 특정 비교 대상을 언급하지 않은 경우에는 `compare_with`를 생략하고(또는 빈 배열) 뉴스에서 자동으로 동종 종목을 찾습니다.

### 예시 출력 (사용자 지정 비교 대상 없음)
[
  {{"step": 1, "tool": "analyze_drivers", "args": {{"ticker": "005930.KS", "name": "삼성전자"}}, "reason": "주가에 가장 큰 영향을 주는 핵심 요인을 파악하기 위해서입니다."}},
  {{"step": 2, "tool": "stock_price", "args": {{"ticker": "005930.KS", "market": "KR"}}, "reason": "현재 주가와 일별 변동 상황을 확인합니다."}},
  {{"step": 3, "tool": "stock_technical", "args": {{"ticker": "005930.KS"}}, "reason": "지지·저항 구간 등 기술적 흐름을 분석합니다."}},
  {{"step": 4, "tool": "stock_news", "args": {{"query": "삼성전자 HBM"}}, "reason": "HBM 관련 뉴스가 최근 주가에 미치는 영향을 확인합니다."}},
  {{"step": 5, "tool": "analyze_peers", "args": {{"ticker": "005930.KS"}}, "reason": "동일 섹터 내 동종 종목과의 추세 상관관계를 분석합니다."}},
  {{"step": 6, "tool": "calculate_risk", "args": {{"ticker": "005930.KS", "market": "KR"}}, "reason": "목표가·손절가·손익비를 계산해 진입 매력도를 평가합니다."}}
]

### 예시 출력 (사용자가 \"SK하이닉스랑 비교해서\"라고 명시한 경우)
[
  ...
  {{"step": 5, "tool": "analyze_peers", "args": {{"ticker": "005930.KS", "compare_with": ["000660.KS"]}}, "reason": "사용자가 지정한 SK하이닉스와의 상대 비교를 수행합니다."}}
  ...
]

마지막으로, **JSON 배열만** 출력하고 그 외의 설명 텍스트는 절대 추가하지 마세요.
모든 reason 필드는 한국어로 작성합니다.""",
            },
            {
                "role": "user",
                "content": f"다음 작업에 대한 실행 계획을 JSON 배열로 만들어 주세요: {user_task}",
            },
        ]
        
        response = self._call_llm(planner_prompt)
        
        # Parse the plan
        try:
            # Try to extract JSON from response
            json_match = re.search(r'\[[\s\S]*\]', response)
            if json_match:
                plan = json.loads(json_match.group(0))
                print(f"   Plan created with {len(plan)} steps")
                return plan
        except json.JSONDecodeError as e:
            print(f"   Failed to parse plan: {e}")
        
        # Fallback: return empty plan
        return []

    def _call_executor(self, step: Dict, tool_result: str, accumulated_context: str) -> str:
        """
        실행 에이전트 LLM: 도구 결과를 해석하고 핵심 인사이트를 뽑아냅니다.
        2~3문장 이내의 한국어 요약을 반환합니다.
        """
        print(f"\n[Executor] {step.get('step', '?')}단계 처리 중: {step.get('tool', 'unknown')}")
        
        executor_prompt = [
            {
                "role": "system",
                "content": """당신은 주식 분석용 **실행 에이전트(Execution Agent)**입니다.
도구 호출 결과를 해석하여 핵심 인사이트만 간결하게 요약해야 합니다.

요약 시에는 다음에 집중하세요:
- 핵심 숫자·지표 (가격, 등락률, 밸류에이션 등)
- 중요한 시그널 (상승/하락, 과매수/과매도 등)
- 주목할 만한 트렌드나 뉴스 포인트

응답은 반드시 **한국어**로, 2~3문장 이내로 작성하세요.""",
            },
            {
                "role": "user",
                "content": f"""단계 설명: {step.get('reason', '도구 실행')}
사용 도구: {step.get('tool')}

[도구 출력]
{tool_result[:2000]}

[이전 단계 요약 컨텍스트]
{accumulated_context[-1000:] if accumulated_context else '없음'}

위 도구 출력에서 **가장 중요한 내용만** 한국어로 2~3문장으로 요약해 주세요.""",
            },
        ]
        
        response = self._call_llm(executor_prompt)
        return response

    def _call_summarizer(self, user_task: str, all_findings: str) -> str:
        """
        플래너 LLM을 사용해 최종 한국어 분석 리포트를 생성합니다.
        """
        print("\n[Planner] 최종 요약 리포트를 생성합니다...")
        
        summary_prompt = [
            {
                "role": "system",
                "content": """당신은 전문 **주식 애널리스트 AI**입니다.
지금까지 수집된 모든 정보를 바탕으로 최종 투자 리포트를 작성합니다.

리포트에는 아래 항목들을 구조적으로 포함하세요:
1. 현재 상황 요약: 현재가, 단기·중기 추세
2. 기술적 분석 요약: 주요 지표(RSI, MACD, 볼린저밴드, 이동평균선 등)와 해석
3. 펀더멘털 요인: 실적, 밸류에이션, 재무 상태 등 핵심 포인트
4. 뉴스·수급/심리: 최근 뉴스 흐름과 투자심리(외국인/기관 수급 포함)
5. **리스크 관리** (매우 중요, 데이터가 있을 경우 반드시 포함):
   - 목표가(Target Price): [가격] ([+X.X%])
   - 손절가(Stop-loss): [가격] ([-X.X%])
   - 손익비(Risk/Reward): [X.X]:1
   - 진입 매력도(Entry Rating): [EXCELLENT/GOOD/FAIR/POOR]
6. 최종 투자 의견: BUY / HOLD / SELL 중 하나를 선택하고, 그 근거를 간결히 제시

톤은 전문적이되 과도하게 장황하지 않게 유지하세요.
리스크 관리 정보(목표가·손절가·손익비)가 `findings`에 포함되어 있다면 **반드시** 리포트에 반영해야 합니다.

모든 답변은 **한국어**로 작성하세요.""",
            },
            {
                "role": "user",
                "content": f"""사용자 요청:
{user_task}

지금까지 수집·요약된 정보:
{all_findings}

위 정보를 기반으로 최종 한국어 분석 리포트와 투자 의견(BUY/HOLD/SELL, 목표가·손절가·손익비 포함)을 작성해 주세요.""",
            },
        ]
        
        response = self._call_llm(summary_prompt)
        return response

    def _call_reflector(self, user_task: str, analysis: str, peer_context: dict = None, tech_data: dict = None) -> str:
        """
        셀프 리플렉터: 최종 분석 내용의 논리적 일관성과 완결성을 점검합니다.
        Reference Proxy가 있을 경우 섹터/벤치마크와의 정합성을 함께 검증합니다.
        """
        print("\n[Reflector] 자기 점검(Self-reflection)을 수행합니다...")
        
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
                    verification_notes.append(f"Reference Proxy {proxy_name}의 추세({proxy_trend})와 신호가 정렬되어 있습니다.")
                elif (proxy_bullish and our_bearish) or (not proxy_bullish and our_bullish):
                    confidence_level = "Low"
                    verification_notes.append(f"섹터 추세와 신호가 상충합니다: {proxy_name}는 {proxy_trend}, 우리 신호는 {our_signal}")
                else:
                    verification_notes.append(f"참고용 Proxy: {proxy_name} ({proxy_trend}, corr={proxy_corr:.2f})")
            
            print(f"   Reference Proxy 확인 완료: {proxy_name} ({proxy_trend})")
        elif peer_context:
            verification_notes.append("높은 상관관계의 Proxy가 없어 독립적인 분석으로 간주합니다.")
            print("   Reference Proxy 없음")
        
        print(f"   추론 신뢰도(Confidence Level): {confidence_level}")
        
        reflection_prompt = [
            {
                "role": "system",
                "content": f"""당신은 주식 리포트의 품질을 검토하는 **크리티컬 리뷰 에이전트**입니다.
아래 항목에 따라 분석 내용을 점검하고, 필요 시 수정안을 제시하세요.

1. **논리적 일관성 검사**
   - 기술적 지표와 최종 추천이 서로 모순되지 않는지 확인합니다.
   - 예: RSI < 30 (과매도)인데 SELL 의견이면 논리적 오류입니다.
   - 예: 긍정적인 뉴스 + 상승 추세인데 SELL 의견이면 근거를 재검토해야 합니다.

2. **내용의 완결성 검사**
   - 가격과 추세 정보가 포함되어 있는지
   - 최소 2~3개의 핵심 기술 지표가 포함되어 있는지
   - 변동성이 큰 종목에 대한 리스크 경고가 있는지
   - 명확한 BUY/HOLD/SELL 의견과 근거가 제시되어 있는지

3. **Reference Proxy 검증 (중요)**
   - 현재 신뢰도(Confidence Level): {confidence_level}
   - 검증 메모: {'; '.join(verification_notes) if verification_notes else 'N/A'}
   - Confidence가 "Low"인 경우: 섹터/벤치마크 추세와 상충된다는 **경고 문구**를 추가합니다.
   - Confidence가 "High"인 경우: 섹터와의 강한 정렬(alignment)을 언급합니다.

4. **자신감 수준 점검**
   - 데이터가 제한적인데 과도하게 확신하는 표현이 있는지 확인합니다.
   - 불확실성이 있는 부분은 솔직하게 언급합니다.

문제가 발견되면, 원문을 참고하여 **수정된 한국어 분석문**을 새로 작성하세요.
문제가 없다면 아래 형식으로 그대로 승인합니다:
"APPROVED: [original analysis]"

5. **리스크 허용도 반영**
   - 사용자의 리스크 허용도: **{risk_tolerance}**
   - 리스크 허용도가 낮다면 보수적인 톤을, 높다면 다소 공격적인 톤을 허용할 수 있습니다.

응답은 반드시 한국어로 작성하되, 승인 시에는 반드시 "APPROVED:" 접두어를 그대로 사용하세요.""",
            },
            {
                "role": "user",
                "content": f"""사용자 요청:
{user_task}

검토 대상 분석문:
{analysis}

위 분석을 검토하여 승인(APPROVED)하거나, 필요한 경우 보완·수정된 버전을 한국어로 작성해 주세요.""",
            },
        ]
        
        response = self._call_llm(reflection_prompt)
        
        if response.startswith("APPROVED:"):
            print("   분석 내용이 수정 없이 승인되었습니다.")
            return analysis
        else:
            print("   자기 점검 결과, 분석 내용이 보완되었습니다.")
            return response

    async def run(self, user_task: str):
        print(f"\n[MementoAgent] 다음 작업을 시작합니다: {user_task}")
        
        # 1. Memory Retrieval
        print("이전 유사 사례(trajectory)를 조회합니다...")
        trajectories = self.memory.retrieve_similar(user_task)
        context_examples = ""
        if trajectories:
            print(f"   유사한 예제가 {len(trajectories)}개 발견되었습니다.")
            context_examples = "과거에 성공적으로 수행된 유사 작업들의 계획과 결과입니다:\n"
            for i, traj in enumerate(trajectories):
                context_examples += (
                    f"--- 예시 {i+1} ---\n"
                    f"Task: {traj['task']}\n"
                    f"Plan: {traj['plan']}\n"
                    f"Result: {traj['result']}\n"
                    f"------------------\n"
                )
        else:
            print("   유사한 예제가 없습니다.")

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
                    {
                        "role": "system",
                        "content": f"""당신은 전문 **주식 분석 AI 어시스턴트**입니다.

## 전문 역량
- 기술적 분석: RSI, MACD, 볼린저 밴드, 이동평균선 등
- 펀더멘털 분석: PER, PBR, ROE, EPS, 재무제표 해석
- AI 예측: Chronos 시계열 + FinBERT 감성 분석
- 실시간 뉴스 및 수급·시장 심리 분석

## 사용자 설정
- **리스크 허용도(Risk Tolerance)**: {get_setting("risk_tolerance", "Medium")}
- **기본 시장(Default Market)**: {get_setting("default_market", "KR")}

## 사용자 작업
{user_task}

## 참고용 과거 성공 사례
{context_examples}

## 사용 가능한 도구
{tool_descriptions}

## 응답 가이드라인
1. **항상 데이터 검증**: 의견을 주기 전에 반드시 도구를 통해 최신 데이터를 확인합니다.
2. **입체적 분석**: 기술적·펀더멘털·뉴스·수급 요인을 함께 고려합니다.
3. **리스크 공시**: 투자에는 손실 가능성이 있음을 항상 언급합니다.
4. **명확한 추천**: BUY / HOLD / SELL 형태의 행동 가능한 인사이트를 제공합니다.

## 도구 호출 형식
도구를 호출할 때는 아래와 같이 **JSON 블록만** 출력합니다.
{{"tool": "tool_name", "arguments": {{"arg_name": "value"}}}}

## 완료 형식
분석을 모두 마쳤다면, 아래 형식으로 한국어 최종 요약을 포함해 출력합니다.
DONE: [한국어로 작성된 종합 주식 분석 요약 및 최종 추천]

답변과 요약, 분석 리포트는 모두 **한국어**로 작성해야 합니다.""",
                    },
                    {
                        "role": "user",
                        "content": f"위 지침에 따라 다음 작업을 수행해 주세요: {user_task}",
                    },
                ]

                plan_text = ""
                final_result = ""
                
                print("\n생각 중입니다(Planning & Tool Calling)...")
                for _ in range(10):
                    content = self._call_llm(history)
                    print(f"\n[Agent 응답 미리보기] {content[:500]}...")
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
                                print(f"도구 실행: {tool_name} 인자={args}")
                                result = await session.call_tool(tool_name, arguments=args)
                                tool_output = result.content[0].text
                                print(f"   도구 결과 일부: {tool_output[:200]}...")
                                history.append(
                                    {
                                        "role": "user",
                                        "content": f"Tool Output ({tool_name}): {tool_output}",
                                    }
                                )
                    except Exception as e:
                        print(f"   도구 실행 중 오류 발생: {e}")
                        history.append({"role": "user", "content": f"Error: {e}"})
        
                # 4. Save to Memory
                self.memory.save_trajectory(user_task, plan_text, final_result, 1.0)
                print("\n작업이 완료되었고, Trajectory가 메모리에 저장되었습니다.")

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
            context_examples = "과거에 성공적으로 수행된 유사 작업들의 계획과 결과입니다:\n"
            for i, traj in enumerate(trajectories):
                context_examples += (
                    f"--- 예시 {i+1} ---\n"
                    f"Task: {traj['task']}\n"
                    f"Plan: {traj['plan']}\n"
                    f"Result: {traj['result']}\n"
                    f"------------------\n"
                )

        # 2. Connect to MCP Server
        # Use the same Python executable as the current process for portability (Windows/macOS/Linux)
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
                            print(f"   {tool_name}에 대한 과거 성공 실행 기록 {len(tips)}건을 참조합니다.")
                        
                        try:
                            # Execute tool
                            print(f"   도구 실행 중: {tool_name}")
                            result = await session.call_tool(tool_name, arguments=args)
                            tool_output = result.content[0].text
                            
                            # Capture peer analysis result for Reflector
                            if tool_name == "analyze_peers":
                                try:
                                    peer_data = json.loads(tool_output)
                                    peers_found = peer_data.get("entity_mining", {}).get("found_peers", 0)
                                    
                                    # FALLBACK: If no peers found, use LLM to identify competitors
                                    if peers_found == 0 and not args.get("compare_with"):
                                        print(f"   No peers found, using LLM fallback...")
                                        ticker = args.get("ticker", "")
                                        
                                        # Ask LLM for industry competitors
                                        fallback_prompt = [
                                            {
                                                "role": "system",
                                                "content": "당신은 금융 애널리스트입니다. 경쟁사 티커만 JSON 배열 형태로 반환하세요.",
                                            },
                                            {
                                                "role": "user",
                                                "content": f"{ticker}와 동일 섹터의 핵심 경쟁사 2~3개 티커만 JSON 배열 형태로 알려주세요. 예: [\"TICKER1\", \"TICKER2\"]. 한국 종목은 .KS 접미사를 사용하세요.",
                                            },
                                        ]
                                        llm_response = self._call_llm(fallback_prompt)
                                        
                                        try:
                                            # Parse LLM response for tickers
                                            ticker_match = re.search(r'\[.*?\]', llm_response)
                                            if ticker_match:
                                                competitor_tickers = json.loads(ticker_match.group(0))
                                                print(f"   LLM이 식별한 경쟁사 티커: {competitor_tickers}")
                                                
                                                # Re-call analyze_peers with competitors
                                                retry_result = await session.call_tool(
                                                    "analyze_peers", 
                                                    arguments={"ticker": ticker, "compare_with": competitor_tickers}
                                                )
                                                tool_output = retry_result.content[0].text
                                                peer_data = json.loads(tool_output)
                                                peers_found = peer_data.get("entity_mining", {}).get("found_peers", 0)
                                                print(f"   재시도 성공: {peers_found}개의 peer를 찾았습니다.")
                                        except Exception as e:
                                            print(f"   LLM fallback failed: {e}")
                                    
                                    reference_proxy = peer_data.get("reference_proxy")
                                    peer_context = {
                                        "peers_found": peers_found,
                                        "reference_proxy": reference_proxy,
                                        "synthesis": peer_data.get("synthesis", ""),
                                        "has_high_correlation": reference_proxy is not None,
                                    }
                                    print("   리플렉터 검증용 Peer 컨텍스트를 저장했습니다.")
                                except:
                                    pass
                            
                            # Capture technical signal for alignment check
                            if tool_name == "stock_technical":
                                try:
                                    tech_data = json.loads(tool_output)
                                    print(f"   기술적 분석 추천 신호를 저장했습니다: {tech_data.get('recommendation', 'N/A')}")
                                except:
                                    pass
                            
                            # Executor interprets the result
                            interpretation = self._call_executor(step, tool_output, all_findings)
                            all_findings += (
                                f"\n### Step {step.get('step')}: {step.get('reason', tool_name)}\n"
                                f"{interpretation}\n"
                            )
                            
                            # Save to procedural memory
                            self.procedural_memory.save_tool_execution(
                                tool_name, args, True, interpretation
                            )
                            
                        except Exception as e:
                            print(f"   단계 실행 실패: {e}")
                            all_findings += f"\n### Step {step.get('step')}: 실패 - {str(e)}\n"
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
        task = "최신 AI 관련 뉴스를 찾아줘"
        if len(sys.argv) > 1:
            task = " ".join(sys.argv[1:])
        
        asyncio.run(agent.run(task))
    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception as e:
        print(f"오류가 발생했습니다: {e}")
        import traceback
        traceback.print_exc()
