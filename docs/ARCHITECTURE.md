# Memento Agent Architecture Walkthrough

## Architecture Diagram

```mermaid
graph TD
    User["User Task"] --> MemRetrieval["🧠 Semantic Memory\n(Retrieve Past Plans)"]
    MemRetrieval --> Planner["📋 Planner LLM"]
    
    subgraph Planning Phase
        Planner -->|Generates| Plan["Execution Plan\n(JSON Steps)"]
    end
    
    Plan --> ExecutorLoop
    
    subgraph Execution Phase
        ExecutorLoop["Executor Loop"] -->|Get Step| Executor["🔧 Executor LLM"]
        Executor -->|Query| ProcMem["💡 Procedural Memory\n(Tool Tips)"]
        ProcMem -->|Tips| Executor
        Executor -->|Call| Tools["🛠️ Stock Tools\n(Price, News, Technicals)"]
        Tools -->|Result| Executor
        Executor -->|Save History| ProcMem
        Executor -->|Accumulate| Findings["All Findings"]
    end
    
    Findings --> Summarizer["📊 Summarizer LLM"]
    Summarizer -->|Draft Analysis| Reflector["🔍 Reflector LLM\n(Self-Correction)"]
    Reflector -->|Final Output| Result["Final Result"]
    
    Result -->|Save Trajectory| MemRetrieval
```

### Visual Diagram
![Memento Agent Architecture](img/memento_agent_architecture_1770345568703.png)

## Components

| Component | Method | Purpose |
|-----------|--------|---------|
| **Planner** | `_call_planner()` | Generates execution plan (JSON array) |
| **Executor** | `_call_executor()` | Interprets each tool result |
| **Summarizer** | `_call_summarizer()` | Creates final analysis |
| **Reflector** | `_call_reflector()` | Self-reviews for consistency |

## Memory Types

| Memory | Class | Purpose |
|--------|-------|---------|
| **Semantic** | `MemoryStore` | Planner: past plans & results |
| **Procedural** | `ProceduralMemory` | Executor: tool usage history |

## Verification Results

**Test:** "삼성전자 분석해줘"

**Server Logs:**
```
📋 [Planner] Generating execution plan...
   ✅ Plan created with 7 steps
   ⚡ Executing: stock_price
🔧 [Executor] Processing step 1: stock_price
... (6 more steps)
📊 [Planner] Generating final summary...
🔍 [Reflector] Self-reflection in progress...
   📝 Analysis revised after reflection
```

**Reflector Caught:**
- MACD bearish vs overall bullish inconsistency
- Missing RSI/Bollinger explanation
- Over-specific price forecast

**Result:** Analysis revised with corrections before returning to user.
