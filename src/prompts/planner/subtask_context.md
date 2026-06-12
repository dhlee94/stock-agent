## Subtask Focus [ACTIVE — overrides sector/market-wide rule below]

You are planning for a specific subtask within a domain analysis.

**Focus**: ${focus}
**Context**: ${context}
**Search hints**: ${search_hints}

⚠️ The **Search hints** are the salient terms this subtask exists to investigate. You MUST pass them — translated into the market's language (Korean for `.KS`/`.KQ`, English for US) — as the `stock_news` `query` argument, and reflect them in any other search-driven tool call. Do NOT call `stock_news` with the ticker alone here: that returns a generic feed and silently drops the subtask's actual concern (the exact failure the Reflector is rejecting).

Plan freely for this specific subtask. The rigid "Sector / market-wide queries" template (steps 1-7) does NOT apply here — choose the tools most appropriate for this focus area. Aim for 3-5 steps.
