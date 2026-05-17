# backend/agents/

The LangGraph agentic reasoning engine — the cognitive core of LedgerMind.

## Files

| File | Purpose |
|---|---|
| `state.py` | `FinancialAgentState` TypedDict — the shared state object threaded through every node |
| `graph.py` | DAG construction, conditional routing functions, SqliteSaver checkpointer wiring |
| `nodes.py` | Individual node functions: query_planner, retrieval, quantitative, drafter, critic, format |
| `prompts.py` | All LLM system prompts (query planner, drafter, critic, format decision) |
| `tools/vector_tool.py` | ChromaDB semantic search + BGE reranker, with per-quarter metadata filtering |
| `tools/pandas_tool.py` | LangChain Pandas REPL tool bound to pre-loaded stock CSV and investor XLS DataFrames |

## Graph topology

```
query_planner ─┬─(narrative)────► retrieval ─────────────────┐
               ├─(hybrid)───────► retrieval ─► quantitative ─┤
               ├─(quantitative)─► quantitative ──────────────┤
               └─(chat)──────────────────────────────────────┤
                                                             ▼
                   drafter ─► critic ─┬─(errors)─► drafter (max 2 passes)
                                      └─(ok)─────► format ─► END
```

### Node responsibilities

**query_planner**
- Classifies intent: `narrative`, `quantitative`, `hybrid`, or `chat`
- Resolves coreferences in follow-up questions against the full conversation history
- Outputs `resolved_query` and `intent` for downstream nodes

**retrieval**
- Calls `search_financial_context()` with the resolved query
- Uses `BAAI/bge-large-en-v1.5` for dense retrieval (top-20 candidates)
- Re-scores with `BAAI/bge-reranker-base` cross-encoder, keeps top-5
- Applies quarter metadata pre-filter when the planner identifies a specific quarter
- Populates `state["context"]` and `state["sources"]`

**quantitative**
- Binds a `PandasDataFrameTool` to the stock CSV (`500209.csv`) and 8-sheet investor workbook
- Invokes Gemini with `_QUANT_INSTRUCTION` system prompt; model writes and executes Python
- Appends computed result to `state["context"]` (so hybrid questions get both text + numbers)

**drafter**
- Full analyst persona prompt; receives `resolved_query` + `context` + previous `errors` (if redraft)
- Produces a factual, formatted Markdown answer
- The draft intentionally does NOT go into `state["messages"]` — only the final answer does

**critic**
- Receives the draft and the original context
- Checks for factual discrepancies, unsupported claims, missing key facts
- Returns either an empty `errors` string (pass) or a corrective instruction string (fail → redraft)
- Redraft loop limited by `MAX_REVISIONS = 2`

**format**
- Classifies whether the answer is best delivered as `"pdf"` or `"excel"`
- Sets `state["output_format"]`; the API endpoint calls the appropriate generator

## Multi-turn memory

State is persisted per `session_id` (LangGraph `thread_id`) in `data/agent_memory.sqlite` via `SqliteSaver`. The `messages` field uses the `add_messages` reducer, so history accumulates across turns. Per-turn working fields (`draft`, `context`, `errors`, `revisions`) are reset to empty strings on each new request by the API's `_fresh_turn_input()` helper, preventing stale state bleed.

## LLM used

`gemini-3.1-flash-lite` via `langchain-google-genai`, `temperature=0.0` for deterministic answers.
