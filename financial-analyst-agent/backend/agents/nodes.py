"""LangGraph node functions for the financial-analyst DAG.

Each node receives the :class:`FinancialAgentState` and returns a *partial*
update dict, which LangGraph merges back into the state. The graph wiring lives
in ``graph.py``; this module only implements per-node behaviour.

The working answer lives in ``state["draft"]`` while the Drafter and Critic
iterate on it; only the *final* answer is appended to ``state["messages"]`` (by
the format node), keeping the conversation history clean for follow-up turns.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from backend.agents.prompts import (
    ANALYST_DRAFTER_PROMPT,
    CRITIC_PROMPT,
    FORMAT_DECISION_PROMPT,
    QUERY_PLANNER_PROMPT,
)
from backend.agents.state import FinancialAgentState
from backend.agents.tools.pandas_tool import (
    INVESTOR_DF_NAMES,
    INVESTOR_XLS,
    STOCK_CSV,
    get_tabular_tool,
)
from backend.agents.tools.vector_tool import search_financial_context
from backend.core.config import get_settings

logger = logging.getLogger(__name__)

# gemini-1.5-pro is retired; gemini-3.1-flash-lite is a current, low-cost model
# with native reasoning and tool-calling support (and its own quota bucket).
LLM_MODEL = "gemini-3.1-flash-lite"

# Loop guard: maximum number of Drafter passes before the graph stops, even if
# the Critic is still unsatisfied. Prevents an infinite Drafter <-> Critic cycle.
MAX_REVISIONS = 2

# Conversation history handed to the LLM is capped so a long multi-turn session
# cannot overflow the model's context window. The full history still persists
# in the checkpointer — only the slice sent to the model is bounded.
MAX_HISTORY_MESSAGES = 12

_QUANT_INSTRUCTION = (
    "You are a quantitative analyst. Use the provided pandas REPL tool to "
    "compute an EXACT answer to the user's question from the pre-loaded "
    "DataFrames. Write a single block of pandas code that prints the result. "
    "Do not estimate — always run the tool.\n\n"
    "CRITICAL INSTRUCTIONS:\n"
    "1. Collect ALL your results into a SINGLE final print statement at the end.\n"
    "2. Do NOT use multiple print() calls — they may not all be captured.\n"
    "3. Format the final output as a clear summary with all metrics.\n"
    "4. Example: print(f'RESULTS: Average Daily Shares={x:.2f}, Total Turnover={y:,.0f}')\n\n"
    "COLUMN NAMES (exact spelling):\n"
    "  - 'No.of Shares' (NOT 'Total Traded Quantity' or 'No. of Shares')\n"
    "  - 'Total Turnover (Rs.)' (NOT 'Turnover' or 'Turnover (₹ Cr)')\n"
    "  - 'Close Price', 'High Price', 'Low Price', 'Open Price', 'Date'\n"
    "  - 'No. of Trades', 'WAP', 'Deliverable Quantity'\n\n"
    "If you get a KeyError, it means you referenced a column that does not exist. "
    "Check the EXACT spelling above — column names are case-sensitive and spaces/punctuation matter."
)


@lru_cache(maxsize=1)
def _get_llm() -> ChatGoogleGenerativeAI:
    """Return the process-wide chat model (temperature 0 for determinism)."""
    return ChatGoogleGenerativeAI(
        model=LLM_MODEL,
        google_api_key=get_settings().GEMINI_API_KEY,
        temperature=0.0,
    )


@lru_cache(maxsize=1)
def _get_pandas_tool():
    """Return the cached pandas REPL tool (DataFrames loaded once)."""
    return get_tabular_tool()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def extract_text(message: object) -> str:
    """Return the plain text of a message regardless of content shape.

    Gemini 3.x models return ``content`` as a list of typed blocks (text plus
    reasoning signatures) rather than a bare string; this flattens either form
    to a single string.
    """
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return str(content)


def _last_user_message(state: FinancialAgentState) -> str:
    """Return the text of the most recent human message, or '' if none."""
    for message in reversed(state["messages"]):
        if isinstance(message, HumanMessage):
            return extract_text(message)
    return ""


def _recent_history(state: FinancialAgentState) -> list:
    """Return the most recent slice of the conversation (token-overflow guard)."""
    return list(state["messages"])[-MAX_HISTORY_MESSAGES:]


_QUARTER_WORDS = {"first": "Q1", "second": "Q2", "third": "Q3", "fourth": "Q4"}


def _extract_quarters(text: str) -> list[str]:
    """Detect EVERY fiscal quarter (Q1-Q4, or spelled out) mentioned, in order.

    Returning all quarters — not just the first — is what lets a comparison
    query ("Q1, Q2, Q3 and Q4") retrieve every quarter instead of being
    filtered down to whichever one happened to appear first.
    """
    found: list[str] = []
    for match in re.finditer(r"\bq([1-4])\b", text, flags=re.IGNORECASE):
        quarter = f"Q{match.group(1)}"
        if quarter not in found:
            found.append(quarter)
    for match in re.finditer(
        r"\b(first|second|third|fourth)[\s-]+quarter\b", text, flags=re.IGNORECASE
    ):
        quarter = _QUARTER_WORDS[match.group(1).lower()]
        if quarter not in found:
            found.append(quarter)

    # A "full year" / "year-to-date" / "annual" query with no explicit quarter
    # is treated as all four quarters, so it gets per-quarter retrieval too.
    if not found and re.search(
        r"\b(full[\s-]?year|entire year|whole year|year[\s-]to[\s-]date|ytd|annual)\b",
        text,
        flags=re.IGNORECASE,
    ):
        return ["Q1", "Q2", "Q3", "Q4"]
    return found


def _parse_planner_output(raw: str) -> tuple[str, str]:
    """Parse the planner's ``QUERY:`` / ``ROUTE:`` reply into (query, route).

    The default route is ``vector_search``, NOT ``direct_answer``: if the
    planner reply is malformed, a financial question must still reach retrieval
    rather than being answered as context-free chit-chat.
    """
    query, route = "", "vector_search"
    for line in raw.splitlines():
        stripped = line.strip()
        upper = stripped.upper()
        if upper.startswith("QUERY:"):
            query = stripped[6:].strip()
        elif upper.startswith("ROUTE:"):
            value = stripped[6:].strip().lower()
            if "hybrid" in value:
                route = "hybrid"
            elif "pandas_calc" in value:
                route = "pandas_calc"
            elif "vector_search" in value:
                route = "vector_search"
            elif "direct_answer" in value:
                route = "direct_answer"
    return query, route


# --------------------------------------------------------------------------- #
# Nodes
# --------------------------------------------------------------------------- #
def query_planner_node(state: FinancialAgentState) -> dict[str, Any]:
    """Resolve follow-up references and classify the routing ``intent``.

    The planner sees the whole conversation, so a question like "and the
    previous quarter?" is rewritten into a self-contained query before any
    retrieval happens.
    """
    history = _recent_history(state)  # bounded prior turns + the current question
    response = _get_llm().invoke([SystemMessage(content=QUERY_PLANNER_PROMPT)] + history)
    resolved_query, route = _parse_planner_output(extract_text(response))

    if not resolved_query:
        # Planner did not echo a QUERY line — fall back to the raw question.
        resolved_query = _last_user_message(state)

    # Unknown routes fall back to "narrative" (retrieval), never "chat" — a
    # financial question must not be answered without evidence.
    intent = {
        "vector_search": "narrative",
        "pandas_calc": "quantitative",
        "hybrid": "hybrid",
        "direct_answer": "chat",
    }.get(route, "narrative")

    logger.info("Planner: intent=%s, resolved_query=%r", intent, resolved_query)
    return {"resolved_query": resolved_query, "intent": intent}


def retrieval_node(state: FinancialAgentState) -> dict[str, Any]:
    """Track A — pull narrative context (and its source documents) from the store."""
    query = state.get("resolved_query") or _last_user_message(state)
    quarters = _extract_quarters(query)
    context, sources = search_financial_context(query, quarters)
    logger.info(
        "Retrieval node produced %d chars of context from %d source(s): %s",
        len(context),
        len(sources),
        sources,
    )
    return {"context": context, "sources": sources}


def quantitative_node(state: FinancialAgentState) -> dict[str, Any]:
    """Track B — compute an exact answer via the pandas REPL tool.

    For a hybrid query the retrieval node has already run, so the computed
    result is APPENDED to the existing narrative context rather than replacing
    it. If the model never calls the tool, its prose is an ungrounded guess and
    is explicitly NOT used as evidence.
    """
    query = state.get("resolved_query") or _last_user_message(state)
    prior_context = state.get("context") or ""
    prior_sources = list(state.get("sources") or [])

    print("\n" + "="*80)
    print("QUANTITATIVE NODE DEBUG")
    print("="*80)
    print(f"Query: {query}")
    print("="*80)

    tool = _get_pandas_tool()
    llm_with_tool = _get_llm().bind_tools([tool])
    ai_message = llm_with_tool.invoke(
        [SystemMessage(content=_QUANT_INSTRUCTION), HumanMessage(content=query)]
    )

    if not ai_message.tool_calls:
        # The model did not run the data tool. Its text is an ungrounded guess,
        # so it must NOT become evidence — record an explicit no-result marker.
        logger.warning("Quantitative node: model returned no tool call.")
        print("⚠️  No tool calls made by LLM")
        marker = (
            "[Quantitative tool was not invoked — no calculation was performed, "
            "so no numerical evidence is available for this question.]"
        )
        merged = f"{prior_context}\n\n{marker}" if prior_context else marker
        return {"context": merged, "sources": prior_sources}

    print(f"✓ Tool calls received: {len(ai_message.tool_calls)}")
    print("="*80)

    results: list[str] = []
    code_blocks: list[str] = []
    for idx, call in enumerate(ai_message.tool_calls):
        code = call["args"]
        code_text = code.get("query", "") if isinstance(code, dict) else str(code)
        code_blocks.append(code_text)
        
        print(f"\n[TOOL CALL #{idx+1}]")
        print("-" * 80)
        print("CODE GENERATED BY LLM:")
        print(code_text)
        print("-" * 80)
        
        try:
            output = tool.invoke(code)
            print("✓ CODE EXECUTED SUCCESSFULLY")
            print("OUTPUT FROM PANDAS:")
            print(output)
            full_output = output
        except KeyError as ke:
            # Column name error — provide helpful hint about actual column names
            col_hint = f"\nAvailable stock_df columns: ['Date', 'Open Price', 'High Price', 'Low Price', 'Close Price', 'WAP', 'No.of Shares', 'No. of Trades', 'Total Turnover (Rs.)', 'Deliverable Quantity', '% Deli. Qty to Traded Qty', 'Spread High-Low', 'Spread Close-Open']"
            full_output = f"KeyError: {ke}{col_hint}"
            print(f"✗ KeyError: {ke}")
            print(f"Hint: {col_hint}")
        except Exception as exc:  # noqa: BLE001 - surface REPL errors as context
            full_output = f"Pandas execution error: {exc}"
            print(f"✗ Execution error: {exc}")
        
        results.append(f"Code:\n{code_text}\n\nResult:\n{full_output}")
        print("-" * 80)

    quant_context = "QUANTITATIVE ANALYSIS (computed from the data files):\n" + (
        "\n\n".join(results)
    )
    
    print("\n[FINAL CONTEXT FOR DRAFTER]")
    print("="*80)
    print(quant_context)
    print("="*80 + "\n")
    
    merged_context = (
        f"{prior_context}\n\n{quant_context}" if prior_context else quant_context
    )

    # Cite the data file(s) the generated code actually referenced.
    all_code = " ".join(code_blocks)
    quant_sources: list[str] = []
    if "stock_df" in all_code:
        quant_sources.append(STOCK_CSV)
    if any(name in all_code for name in INVESTOR_DF_NAMES):
        quant_sources.append(INVESTOR_XLS)
    if not quant_sources:
        quant_sources = [STOCK_CSV]
    merged_sources = list(dict.fromkeys(prior_sources + quant_sources))

    logger.info("Quantitative node produced %d chars of context.", len(quant_context))
    return {"context": merged_context, "sources": merged_sources}


def drafter_node(state: FinancialAgentState) -> dict[str, Any]:
    """Synthesise the analyst answer from the assembled context.

    Writes to ``draft`` (not ``messages``) so redraft cycles never pollute the
    conversation history.
    """
    context = state.get("context") or "(no supporting evidence was retrieved)"
    errors = state.get("errors") or ""
    revisions = state.get("revisions", 0) + 1

    print("\n" + "="*80)
    print(f"DRAFTER NODE DEBUG (Revision #{revisions})")
    print("="*80)
    print("CONTEXT RECEIVED BY DRAFTER:")
    print("-" * 80)
    print(context[:1000])  # Print first 1000 chars of context
    if len(context) > 1000:
        print(f"... (truncated, total {len(context)} chars)")
    print("-" * 80)

    # System prompt + the full conversation. The message list ends on the
    # current human turn, so the model always has something to answer.
    llm_messages: list = [
        SystemMessage(content=ANALYST_DRAFTER_PROMPT.format(context=context))
    ]
    llm_messages += _recent_history(state)

    if errors:
        # On a redraft, hand back the rejected draft plus the Critic's feedback.
        print(f"\n[REDRAFT - Errors from previous attempt]")
        print(errors)
        llm_messages.append(
            HumanMessage(
                content="Your previous draft failed fact-check. Correct these "
                f"specific issues and write the full answer again.\n\n"
                f"ISSUES:\n{errors}\n\nPREVIOUS DRAFT:\n{state.get('draft', '')}"
            )
        )

    print("\nCalling LLM drafter...")
    response = _get_llm().invoke(llm_messages)
    draft = extract_text(response)
    
    print("="*80)
    print("DRAFT GENERATED BY LLM:")
    print("="*80)
    print(draft)
    print("="*80 + "\n")
    
    logger.info("Drafter produced draft #%d (%d chars).", revisions, len(draft))
    return {"draft": draft, "revisions": revisions}


def critic_node(state: FinancialAgentState) -> dict[str, Any]:
    """Fact-check the working draft against the context.

    Writes a non-empty ``errors`` string on failure (triggering a redraft) or
    clears it on success.
    """
    context = state.get("context") or ""
    draft = state.get("draft", "")

    print("\n" + "="*80)
    print("CRITIC NODE DEBUG")
    print("="*80)
    print("DRAFT TO AUDIT:")
    print("-" * 80)
    print(draft[:800])
    if len(draft) > 800:
        print(f"... (truncated, total {len(draft)} chars)")
    print("-" * 80)
    print("\nCONTEXT AVAILABLE FOR FACT-CHECK:")
    print("-" * 80)
    print(context[:800])
    if len(context) > 800:
        print(f"... (truncated, total {len(context)} chars)")
    print("-" * 80)

    # Nothing to verify against (e.g. general chat) — accept the draft.
    if not context:
        print("✓ No context to verify against, accepting draft")
        return {"errors": ""}

    # Gemini requires at least one non-system content message, so the audit
    # instruction is delivered as a HumanMessage alongside the system prompt.
    print("\nCalling LLM critic...")
    response = _get_llm().invoke(
        [
            SystemMessage(content=CRITIC_PROMPT.format(context=context, draft=draft)),
            HumanMessage(
                content="Audit the draft answer against the evidence now. "
                "Reply with PASS, or with FAIL: followed by the problems."
            ),
        ]
    )
    verdict = extract_text(response).strip()

    print("="*80)
    print("CRITIC VERDICT:")
    print("="*80)
    print(verdict)
    print("="*80 + "\n")

    if verdict.upper().startswith("PASS"):
        logger.info("Critic: draft PASSED fact-check.")
        print("✓ DRAFT PASSED")
        return {"errors": ""}

    logger.warning("Critic: draft FAILED fact-check — %s", verdict)
    print("✗ DRAFT FAILED - will trigger redraft")
    return {"errors": verdict}


def format_node(state: FinancialAgentState) -> dict[str, Any]:
    """Choose the delivery format and finalise the answer.

    Picks ``pdf`` or ``excel`` based on the answer's nature (every answer is
    delivered as a downloadable file) and appends the final answer to
    ``messages`` as this turn's assistant reply.
    """
    question = state.get("resolved_query") or _last_user_message(state)
    answer = state.get("draft") or "I could not produce an answer."

    # If the Critic's feedback is still unresolved, the revision budget was
    # exhausted with the draft failing — warn the user instead of silently
    # delivering an answer the auditor rejected.
    verified = not (state.get("errors") or "")
    if not verified:
        answer = (
            "> ⚠️ **Unverified answer** — this response did not pass the "
            "automated fact-check. Please verify it against the cited sources "
            "before relying on it.\n\n"
        ) + answer
        logger.warning("Format node: delivering an UNVERIFIED answer.")

    response = _get_llm().invoke(
        [
            SystemMessage(content=FORMAT_DECISION_PROMPT),
            HumanMessage(content=f"QUESTION:\n{question}\n\nANSWER:\n{answer}"),
        ]
    )
    raw = extract_text(response).strip().lower()
    output_format = "excel" if "excel" in raw else "pdf"

    logger.info("Format node selected output_format=%s (raw=%r)", output_format, raw)
    return {
        "output_format": output_format,
        "verified": verified,
        "messages": [AIMessage(content=answer)],
    }
