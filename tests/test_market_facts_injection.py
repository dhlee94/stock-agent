"""
Regression test — canonical market-fact snapshot reaches the worker executor.

The deterministic snapshot from _market_consistency_anchor (price × shares ≈
market cap, 52-week range) used to be fed ONLY to the Global Reflector. Workers
still re-derived aggregate figures off each tool payload, so per-subtask numbers
drifted. Now _run_flow threads `market_facts` down to every subtask's executor
(_call_executor), which prepends it so the executor anchors to the same canonical
values it is already told to check against ("market cap ≠ price × shares …").

This test asserts the snapshot is injected into the executor prompt when present
and absent when empty. Run inside the app image (imports agent_client natively —
do NOT run under test_flows' stubbing):
    docker exec stock-agent-app python -m pytest tests/test_market_facts_injection.py -v
"""
import asyncio
import os
import sys

try:
    import pytest
except ModuleNotFoundError:
    pytest = None

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

FACTS = ("[VERIFIED MARKET FACTS — NFLX]\n"
         "- Price $74.35 × shares 0.430B = $32.0B ≈ market cap $32.0B\n"
         "- Live (extended-hours) price $67.30 vs regular-session close $74.35 "
         "(both real — use $67.30 as the current price).\n"
         "- 52-week range $60.00–$95.00; current price $67.30")

STEP = {"tool": "stock_dcf", "reason": "value the company"}
TOOL_OUT = '{"fair_value": 152.68, "current_price": 67.30}'


def _bare_agent_with_capture(captured):
    """A MementoAgent shell (no __init__ / no MCP/DB) with _call_llm captured."""
    import agent_client
    agent = agent_client.MementoAgent.__new__(agent_client.MementoAgent)

    async def fake_llm(prompt, model=None):
        captured["prompt"] = prompt
        captured["model"] = model
        return "interpreted"

    agent._call_llm = fake_llm
    return agent


def _executor_user_msg(market_facts):
    captured = {}
    agent = _bare_agent_with_capture(captured)
    asyncio.run(agent._call_executor(STEP, TOOL_OUT, "", market_facts=market_facts))
    return captured["prompt"][-1]["content"]


def test_executor_prepends_market_facts_when_present():
    msg = _executor_user_msg(FACTS)
    assert FACTS in msg, "canonical snapshot was not injected into the executor prompt"
    assert msg.startswith("[VERIFIED MARKET FACTS"), "snapshot must lead the executor user message"
    # The tool output is still present after the snapshot.
    assert "fair_value" in msg


def test_executor_omits_prefix_when_no_facts():
    msg = _executor_user_msg("")
    assert not msg.startswith("[VERIFIED MARKET FACTS")
    assert msg.startswith("Step:"), "with no snapshot the executor message is unchanged"


if __name__ == "__main__":
    print("with facts, message head:\n", _executor_user_msg(FACTS)[:200])
    print("\nwithout facts, message head:\n", _executor_user_msg("")[:120])
