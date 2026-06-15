"""
Tests for single-subtask and domain (multi-subtask) flows in agent_client.py.
All LLM and MCP calls are mocked — no API keys or heavy dependencies required.
"""
import asyncio
import json
import sys
import os
import types
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Stub out heavy / external modules BEFORE importing agent_client
# ---------------------------------------------------------------------------

def _stub_module(name, **attrs):
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


# numpy / scipy / torch / transformers / sentence_transformers
for _mod_name in [
    "numpy", "scipy", "scipy.spatial", "torch", "transformers",
    "sentence_transformers", "google", "google.genai",
    "openai", "groq", "anthropic", "mcp", "mcp.client",
    "mcp.client.stdio", "dotenv",
]:
    if _mod_name not in sys.modules:
        _stub_module(_mod_name)

# numpy needs array/ndarray for type checks
_np = sys.modules["numpy"]
_np.ndarray = type("ndarray", (), {})
_np.array = lambda *a, **k: []
_np.dot = lambda a, b: 0.0

# dotenv.load_dotenv
sys.modules["dotenv"].load_dotenv = lambda *a, **k: None

# google.genai.Client
_genai = sys.modules["google.genai"]
_genai.Client = MagicMock()

# mcp stubs
_mcp = sys.modules["mcp"]
_mcp.ClientSession = MagicMock()
_mcp.StdioServerParameters = MagicMock()
_mcp_stdio = sys.modules["mcp.client.stdio"]
_mcp_stdio.stdio_client = MagicMock()

# sentence_transformers.SentenceTransformer
sys.modules["sentence_transformers"].SentenceTransformer = MagicMock(
    return_value=MagicMock(encode=MagicMock(return_value=[0.0]))
)

# Stub database module
_db_mod = _stub_module(
    "database",
    get_setting=MagicMock(return_value=None),
    reembed_if_model_changed=MagicMock(),
    init_db=MagicMock(),
)

# Stub memory_store module
_ms_mod = _stub_module("memory_store")
_ms_mod.MemoryStore = MagicMock()
_ms_mod.SemanticMemory = MagicMock()
_ms_mod.ProceduralMemory = MagicMock()

# Stub driver_memory module
_dm_mod = _stub_module("driver_memory")
_dm_mod.DriverMemory = MagicMock()

# Stub kr/us listing lookups
_kr_mod = _stub_module("tools.stock.kr_listing", lookup_kr_ticker=MagicMock(return_value=None))
_us_mod = _stub_module(
    "tools.stock.us_listing",
    lookup_us_ticker=MagicMock(return_value=None),
    is_valid_us_ticker=MagicMock(return_value=True),
)
_mu_mod = _stub_module("tools.stock.market_utils", NAME_TO_TICKER={})

# tools sub-packages must be importable
for _pkg in ["tools", "tools.stock"]:
    if _pkg not in sys.modules:
        _stub_module(_pkg)

# Stub prompts package
_prompts_mod = _stub_module("prompts")
_prompts_mod.load_prompt = MagicMock(return_value="[mocked prompt]")

# Use the REAL config module instead of a hand-maintained stub, so this test
# automatically stays in sync with whatever agent_client imports from config.
# (Previously, adding a new config constant — e.g. MEMORY_COMPRESSOR_MODEL —
# silently broke test collection with an ImportError.)
#
# This is safe: config.py only reads os.environ with defaults — no network,
# DB, or key validation — and dotenv.load_dotenv is stubbed to a no-op above,
# so the developer's local .env is never read. We clear the provider API keys
# first so behavior is deterministic regardless of the shell environment
# (the SDK clients are stubbed either way).
for _k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY",
           "GROQ_API_KEY", "ANTHROPIC_API_KEY"):
    os.environ.pop(_k, None)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import config  # noqa: E402  (real module — keeps this test in sync with product)
import agent_client  # noqa: E402
from agent_client import (  # noqa: E402
    MementoAgent, _findings_usable, _build_trajectory_meta,
    _is_retryable_error, _parse_llm_json,
)

# ---------------------------------------------------------------------------
# Data fixtures
# ---------------------------------------------------------------------------

SINGLE_PLAN = {
    "subject": "삼성전자 (005930.KS)",
    "key_points": ["어때"],
    "forecast_horizon": 5,
    "search_keywords": [],
    "notes": "General status check.",
    "subtasks": [
        {"focus": "삼성전자 종합분석", "search_hints": [], "context": "전반 분석"}
    ],
}

DOMAIN_PLAN = {
    "subject": "바이오 섹터",
    "key_points": ["바이오주", "전망"],
    "forecast_horizon": 20,
    "search_keywords": ["바이오"],
    "notes": "Sector-level forward-looking question.",
    "subtasks": [
        {"focus": "제약", "search_hints": ["제약 실적"], "context": "대형 제약사"},
        {"focus": "바이오텍", "search_hints": ["FDA 승인"], "context": "임상 이슈"},
        {"focus": "의료기기", "search_hints": ["의료기기 수출"], "context": "수출 모멘텀"},
    ],
}


def _make_agent():
    """Return a MementoAgent with all I/O attributes replaced by mocks."""
    a = MementoAgent.__new__(MementoAgent)
    a.memory = MagicMock()
    a.semantic_memory = MagicMock()
    a.procedural_memory = MagicMock()
    a.procedural_memory.get_tool_tips = MagicMock(return_value=[])
    a.procedural_memory.save_tool_execution = MagicMock()
    a.driver_memory = MagicMock()
    a._mcp_session = None
    a._mcp_exit_stack = None
    a._mcp_tools_desc = ""
    a._mcp_lock = None
    return a


def _tool_session(text="{}"):
    result_mock = MagicMock()
    result_mock.content = [MagicMock(text=text)]
    session = MagicMock()
    session.call_tool = AsyncMock(return_value=result_mock)
    return session


# ---------------------------------------------------------------------------
# _call_global_planner
# ---------------------------------------------------------------------------

class TestCallGlobalPlanner:
    @pytest.mark.asyncio
    async def test_single_query_returns_one_subtask(self):
        agent = _make_agent()
        agent._call_llm = AsyncMock(return_value=json.dumps(SINGLE_PLAN))

        result = await agent._call_global_planner("삼성전자 어때?")

        assert result["subject"] == "삼성전자 (005930.KS)"
        assert len(result["subtasks"]) == 1
        assert result["subtasks"][0]["focus"] == "삼성전자 종합분석"

    @pytest.mark.asyncio
    async def test_domain_query_returns_multiple_subtasks(self):
        agent = _make_agent()
        agent._call_llm = AsyncMock(return_value=json.dumps(DOMAIN_PLAN))

        result = await agent._call_global_planner("바이오주 전망 어때?")

        assert result["subject"] == "바이오 섹터"
        assert len(result["subtasks"]) == 3

    @pytest.mark.asyncio
    async def test_malformed_json_returns_empty_dict(self):
        agent = _make_agent()
        agent._call_llm = AsyncMock(return_value="No JSON here.")

        result = await agent._call_global_planner("anything")

        assert result == {}

    @pytest.mark.asyncio
    async def test_partial_json_with_extra_text(self):
        agent = _make_agent()
        payload = "Here is my plan:\n" + json.dumps(SINGLE_PLAN) + "\nDone."
        agent._call_llm = AsyncMock(return_value=payload)

        result = await agent._call_global_planner("삼성전자 어때?")

        assert result["subject"] == "삼성전자 (005930.KS)"


# ---------------------------------------------------------------------------
# _run_flow — single subtask path
# ---------------------------------------------------------------------------

class TestRunFlowSingle:
    @pytest.mark.asyncio
    async def test_single_subtask_calls_summarizer(self):
        agent = _make_agent()
        session = _tool_session('{"price": 70000}')

        agent._call_planner = AsyncMock(return_value=[
            {"step": 1, "tool": "stock_price", "args": {"ticker": "005930.KS"}, "reason": "Get price"}
        ])
        agent._call_executor = AsyncMock(return_value="현재가 70,000원. 안정적.")
        agent._call_local_reflector = AsyncMock(return_value={"valid": True, "issues": []})
        agent._call_global_reflector = AsyncMock(return_value={"approved": True})
        agent._call_summarizer = AsyncMock(return_value="삼성전자 최종 분석: 보유 추천")

        result, _meta = await agent._run_flow(
            user_task="삼성전자 어때?",
            global_plan=SINGLE_PLAN,
            session=session,
            tool_descriptions="- stock_price: ...",
            context_examples="",
            semantic_knowledge=[],
        )

        assert result == "삼성전자 최종 분석: 보유 추천"
        agent._call_summarizer.assert_awaited_once()
        assert agent._call_planner.await_count == 1

    @pytest.mark.asyncio
    async def test_single_subtask_retries_on_invalid_local_check(self):
        agent = _make_agent()
        session = _tool_session()

        agent._call_planner = AsyncMock(return_value=[
            {"step": 1, "tool": "stock_price", "args": {}, "reason": "price"}
        ])
        agent._call_executor = AsyncMock(return_value="empty result")
        agent._call_local_reflector = AsyncMock(side_effect=[
            {"valid": False, "issues": ["No data"]},
            {"valid": True, "issues": []},
        ])
        agent._call_global_reflector = AsyncMock(return_value={"approved": True})
        agent._call_summarizer = AsyncMock(return_value="요약 완료")

        await agent._run_flow(
            user_task="삼성전자 어때?",
            global_plan=SINGLE_PLAN,
            session=session,
            tool_descriptions="",
            context_examples="",
            semantic_knowledge=[],
        )

        # Planner called twice: initial + retry
        assert agent._call_planner.await_count == 2


# ---------------------------------------------------------------------------
# _run_flow — domain (multi-subtask) path
# ---------------------------------------------------------------------------

class TestRunFlowDomain:
    @pytest.mark.asyncio
    async def test_domain_three_subtasks_all_run(self):
        agent = _make_agent()
        session = _tool_session()

        agent._call_planner = AsyncMock(return_value=[
            {"step": 1, "tool": "search_web", "args": {"query": "바이오"}, "reason": "뉴스"}
        ])
        agent._call_executor = AsyncMock(return_value="섹터 동향 분석 완료")
        agent._call_local_reflector = AsyncMock(return_value={"valid": True, "issues": []})
        agent._call_global_reflector = AsyncMock(return_value={"approved": True})
        agent._call_summarizer = AsyncMock(return_value="바이오 섹터 최종 요약")

        result, _meta = await agent._run_flow(
            user_task="바이오주 전망 어때?",
            global_plan=DOMAIN_PLAN,
            session=session,
            tool_descriptions="",
            context_examples="",
            semantic_knowledge=[],
        )

        assert result == "바이오 섹터 최종 요약"
        # One planner call per subtask (3), no retry
        assert agent._call_planner.await_count == 3
        assert agent._call_local_reflector.await_count == 3

    @pytest.mark.asyncio
    async def test_domain_global_reflector_rejection_triggers_judge(self):
        agent = _make_agent()
        session = _tool_session()

        agent._call_planner = AsyncMock(return_value=[
            {"step": 1, "tool": "search_web", "args": {}, "reason": "search"}
        ])
        agent._call_executor = AsyncMock(return_value="분석")
        agent._call_local_reflector = AsyncMock(return_value={"valid": True, "issues": []})
        # First global check rejected → triggers debate
        agent._call_global_reflector = AsyncMock(return_value={
            "approved": False, "critique": "CMO 섹터 누락",
            "missing_coverage": ["CMO"], "weak_points": [],
        })
        agent._call_global_planner_defense = AsyncMock(return_value={
            "defense": "CMO는 현재 데이터 부족",
            "concede": ["CMO"],
            "new_subtasks": [],
        })
        agent._call_judge = AsyncMock(return_value={
            "verdict": "planner",
            "reason": "CMO 데이터 부족 인정",
        })
        agent._call_summarizer = AsyncMock(return_value="최종 요약 (planner wins)")

        result, _meta = await agent._run_flow(
            user_task="바이오주 전망 어때?",
            global_plan=DOMAIN_PLAN,
            session=session,
            tool_descriptions="",
            context_examples="",
            semantic_knowledge=[],
        )

        agent._call_global_reflector.assert_awaited_once()
        agent._call_global_planner_defense.assert_awaited_once()
        agent._call_judge.assert_awaited_once()
        assert "planner wins" in result

    @pytest.mark.asyncio
    async def test_domain_judge_reflector_wins_queues_new_subtasks(self):
        agent = _make_agent()
        session = _tool_session()

        new_subtask = {"focus": "CMO/CDMO", "search_hints": ["CDMO"], "context": "위탁생산"}

        agent._call_planner = AsyncMock(return_value=[
            {"step": 1, "tool": "search_web", "args": {}, "reason": "search"}
        ])
        agent._call_executor = AsyncMock(return_value="분석")
        agent._call_local_reflector = AsyncMock(return_value={"valid": True, "issues": []})
        agent._call_global_reflector = AsyncMock(side_effect=[
            {"approved": False, "critique": "CMO 누락", "missing_coverage": ["CMO"], "weak_points": []},
            {"approved": True},
        ])
        agent._call_global_planner_defense = AsyncMock(return_value={
            "defense": "추가 분석 가능",
            "concede": [],
            "new_subtasks": [new_subtask],
        })
        agent._call_judge = AsyncMock(return_value={
            "verdict": "reflector",
            "reason": "CMO 분석 필요",
        })
        agent._call_summarizer = AsyncMock(return_value="CMO 포함 최종 요약")

        result, _meta = await agent._run_flow(
            user_task="바이오주 전망 어때?",
            global_plan=DOMAIN_PLAN,
            session=session,
            tool_descriptions="",
            context_examples="",
            semantic_knowledge=[],
        )

        agent._call_summarizer.assert_awaited_once()
        # Two global iterations — second pass with new subtask
        assert agent._call_global_reflector.await_count == 2
        assert "CMO" in result


# ---------------------------------------------------------------------------
# _run_flow — empty subtasks fallback
# ---------------------------------------------------------------------------

class TestRunFlowEmptySubtasks:
    @pytest.mark.asyncio
    async def test_empty_global_plan_produces_empty_findings(self):
        agent = _make_agent()
        session = _tool_session()

        agent._call_planner = AsyncMock(return_value=[])
        agent._call_local_reflector = AsyncMock(return_value={"valid": True})
        agent._call_global_reflector = AsyncMock(return_value={"approved": True})
        agent._call_summarizer = AsyncMock(return_value="결과 없음")

        await agent._run_flow(
            user_task="anything",
            global_plan={},
            session=session,
            tool_descriptions="",
            context_examples="",
            semantic_knowledge=[],
        )

        agent._call_planner.assert_not_awaited()
        agent._call_summarizer.assert_awaited_once()


# ---------------------------------------------------------------------------
# _run_flow — per-run tool-result cache (dedup of identical tool calls)
# ---------------------------------------------------------------------------

class TestRunFlowToolCache:
    @pytest.mark.asyncio
    async def test_identical_tool_calls_collapse_to_one(self):
        """3 parallel subtasks requesting the SAME tool+args hit call_tool once.

        Guards the fix for the NFLX runaway: ticker-level tools (e.g. Moirai)
        were recomputed once per subtask. Without the cache this asserts 3.
        """
        agent = _make_agent()
        session = _tool_session('{"price": 70000}')

        same_step = [{"tool": "stock_price", "args": {"ticker": "005930.KS"}, "reason": "price"}]
        agent._call_planner = AsyncMock(return_value=same_step)
        agent._call_executor = AsyncMock(return_value="현재가 70,000원.")
        agent._call_local_reflector = AsyncMock(return_value={"valid": True})
        agent._call_global_reflector = AsyncMock(return_value={"approved": True})
        agent._call_summarizer = AsyncMock(return_value="요약")

        await agent._run_flow(
            user_task="바이오주 전망 어때?",
            global_plan=DOMAIN_PLAN,            # 3 subtasks
            session=session,
            tool_descriptions="",
            context_examples="",
            semantic_knowledge=[],
        )

        # 3 subtasks × identical (tool, args) → exactly one real tool call.
        assert session.call_tool.await_count == 1

    @pytest.mark.asyncio
    async def test_distinct_args_are_not_collapsed(self):
        """Same tool with different args must NOT share a cache entry."""
        agent = _make_agent()
        session = _tool_session('{"price": 70000}')

        # Each subtask asks stock_price for a different ticker.
        tickers = iter(["005930.KS", "000660.KS", "035420.KS"])
        agent._call_planner = AsyncMock(
            side_effect=lambda *a, **k: [
                {"tool": "stock_price", "args": {"ticker": next(tickers)}, "reason": "price"}
            ]
        )
        agent._call_executor = AsyncMock(return_value="현재가.")
        agent._call_local_reflector = AsyncMock(return_value={"valid": True})
        agent._call_global_reflector = AsyncMock(return_value={"approved": True})
        agent._call_summarizer = AsyncMock(return_value="요약")

        await agent._run_flow(
            user_task="바이오주 전망 어때?",
            global_plan=DOMAIN_PLAN,            # 3 subtasks
            session=session,
            tool_descriptions="",
            context_examples="",
            semantic_knowledge=[],
        )

        assert session.call_tool.await_count == 3

    @pytest.mark.asyncio
    async def test_identical_raw_block_embedded_once(self):
        """The raw [원본 수치] digest is embedded once per run; repeats become a reference
        so the same block isn't copy-pasted verbatim across subtasks (Reflector padding)."""
        agent = _make_agent()
        session = _tool_session('{"price": 70000}')

        same_step = [{"tool": "stock_price", "args": {"ticker": "005930.KS"}, "reason": "price"}]
        agent._call_planner = AsyncMock(return_value=same_step)
        agent._call_executor = AsyncMock(return_value="현재가 70,000원.")
        agent._call_local_reflector = AsyncMock(return_value={"valid": True})
        agent._call_global_reflector = AsyncMock(return_value={"approved": True})
        agent._call_summarizer = AsyncMock(return_value="요약")

        await agent._run_flow(
            user_task="바이오주 전망 어때?",
            global_plan=DOMAIN_PLAN,            # 3 subtasks, identical tool+args
            session=session,
            tool_descriptions="",
            context_examples="",
            semantic_knowledge=[],
        )

        # The summarizer receives the full combined findings — inspect dedup there.
        findings = agent._call_summarizer.call_args[0][1]
        assert findings.count("[원본 수치] {") == 1            # raw digest embedded once
        assert findings.count("이미 제시됨") == 2              # other two are references


# ---------------------------------------------------------------------------
# Episodic-trajectory metadata — the fix for the dead learning loop (A)
# ---------------------------------------------------------------------------

class TestTrajectoryMeta:
    def test_findings_usable(self):
        assert _findings_usable("\n### 가격\n현재가 70000원\n") is True
        assert _findings_usable("\n### 뉴스: Failed - timeout\n") is False
        # mixed: one failed section, one good → usable
        assert _findings_usable("\n### 가격: Failed - x\n\n### 재무\nPER 12\n") is True
        assert _findings_usable("") is False
        assert _findings_usable("   ") is False

    def test_score_varies_by_outcome(self):
        fbf = {"가격": "### 가격\n70000"}
        vbf = {"가격": True}
        scores = {
            o: _build_trajectory_meta(o, {}, fbf, vbf, {})["score"]
            for o in ("approved_early", "approved_late", "judge_planner", "maxed")
        }
        # Must differ — a constant score is what froze the overwrite gate.
        assert len(set(scores.values())) == 4
        assert scores["approved_early"] > scores["maxed"]

    def test_plan_prunes_dead_focuses(self):
        fbf = {
            "가격": "### 가격\n70000",
            "뉴스": "### 뉴스: Failed - x",   # failed → drop
            "재무": "### 재무\nPER 12",
            "빈것": "",                        # empty → drop
        }
        vbf = {"가격": True, "뉴스": False, "재무": True, "빈것": True}
        meta = _build_trajectory_meta("approved_early", {}, fbf, vbf, {})
        kept = json.loads(meta["plan"])
        assert kept == ["가격", "재무"]

    def test_lessons_only_on_unapproved_with_gaps(self):
        fbf = {"가격": "### 가격\n70000"}
        vbf = {"가격": True}
        crit = {"missing_coverage": ["CMO 분석"], "weak_points": ["밸류 근거 약함"]}
        assert _build_trajectory_meta("approved_early", crit, fbf, vbf, {})["lessons"] == []
        maxed = _build_trajectory_meta("maxed", crit, fbf, vbf, {})["lessons"]
        assert any("CMO" in l for l in maxed)
        assert all(l.startswith("보완 필요:") for l in maxed)


# ---------------------------------------------------------------------------
# LLM-call robustness — retry/backoff (B), atomic rate limit (C), parse (D)
# ---------------------------------------------------------------------------

class TestRetryableError:
    def test_status_codes(self):
        e = type("E", (Exception,), {})()
        e.status_code = 429
        assert _is_retryable_error(e) is True
        e.status_code = 400
        assert _is_retryable_error(e) is False

    def test_by_class_name(self):
        assert _is_retryable_error(type("RateLimitError", (Exception,), {})())
        assert _is_retryable_error(type("APITimeoutError", (Exception,), {})())
        assert not _is_retryable_error(type("AuthenticationError", (Exception,), {})("bad key"))

    def test_by_message(self):
        assert _is_retryable_error(Exception("Error code: 503 temporarily unavailable"))
        assert not _is_retryable_error(Exception("invalid api key"))


class TestParseLlmJson:
    def test_plain(self):
        assert _parse_llm_json('{"approved": true}') == {"approved": True}

    def test_with_prose_and_fences(self):
        txt = 'Here:\n```json\n{"valid": false, "issues": ["x"]}\n```\nDone.'
        assert _parse_llm_json(txt) == {"valid": False, "issues": ["x"]}

    def test_unparseable_returns_none(self):
        assert _parse_llm_json("no json here") is None
        assert _parse_llm_json("") is None
        assert _parse_llm_json("{broken: ,}") is None


class TestCallLlmRetry:
    @pytest.mark.asyncio
    async def test_retries_transient_then_succeeds(self, monkeypatch):
        agent = _make_agent()
        monkeypatch.setattr(agent_client, "MOCK_MODE", False)
        monkeypatch.setattr(agent_client, "_MIN_WAIT", {"groq": 0})

        calls = {"n": 0}

        def _create(**kw):
            calls["n"] += 1
            if calls["n"] == 1:
                raise type("RateLimitError", (Exception,), {})("429 rate limit")
            resp = MagicMock()
            resp.choices = [MagicMock(message=MagicMock(content="OK"))]
            return resp

        fake = MagicMock()
        fake.chat.completions.create = _create
        monkeypatch.setitem(agent_client._provider_clients, "groq", fake)

        with patch("agent_client.asyncio.sleep", AsyncMock()):
            out = await agent._call_llm([{"role": "user", "content": "hi"}], model="llama-3.1")

        assert out == "OK"
        assert calls["n"] == 2          # one retry happened

    @pytest.mark.asyncio
    async def test_non_retryable_raises_immediately(self, monkeypatch):
        agent = _make_agent()
        monkeypatch.setattr(agent_client, "MOCK_MODE", False)
        monkeypatch.setattr(agent_client, "_MIN_WAIT", {"groq": 0})

        calls = {"n": 0}

        def _create(**kw):
            calls["n"] += 1
            raise type("AuthenticationError", (Exception,), {})("invalid api key")

        fake = MagicMock()
        fake.chat.completions.create = _create
        monkeypatch.setitem(agent_client._provider_clients, "groq", fake)

        with patch("agent_client.asyncio.sleep", AsyncMock()):
            with pytest.raises(Exception):
                await agent._call_llm([{"role": "user", "content": "hi"}], model="llama-3.1")

        assert calls["n"] == 1          # no retry on auth error


class TestRateLimitGateAtomic:
    @pytest.mark.asyncio
    async def test_concurrent_calls_are_serialized_not_bursted(self, monkeypatch):
        """The gate must stamp slots one-at-a-time. With the old non-atomic read→
        sleep→write, concurrent coroutines all read the same stale timestamp; here
        we assert each observes the previous one's stamp (strictly increasing)."""
        agent = _make_agent()
        monkeypatch.setattr(agent_client, "_MIN_WAIT", {"groq": 0})
        agent_client._PROVIDER_LOCKS.pop("groq", None)
        agent_client._LAST_API_CALL.pop("groq", None)

        seen = []
        orig = agent._rate_limit_gate

        async def _spy(provider):
            await orig(provider)
            seen.append(agent_client._LAST_API_CALL[provider])

        await asyncio.gather(*[_spy("groq") for _ in range(5)])
        # Each gate pass writes a fresh monotonic stamp under the lock → no two
        # coroutines share a timestamp (the burst bug would produce duplicates).
        assert len(set(seen)) == len(seen)
