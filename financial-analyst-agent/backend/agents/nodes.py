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
from backend.agents.tools.pandas_tool import INVESTOR_XLS, STOCK_CSV, get_tabular_tool
from backend.agents.tools.vector_tool import search_financial_context
from backend.core.config import get_settings

logger = logging.getLogger(__name__)

# gemini-1.5-pro is retired; gemini-3.1-flash-lite is a current, low-cost model
# with native reasoning and tool-calling support (and its own quota bucket).
LLM_MODEL = "gemini-3.1-flash-lite"

# Loop guard: maximum number of Drafter passes before the graph stops, even if
# the Critic is still unsatisfied. Prevents an infinite Drafter <-> Critic cycle.
MAX_REVISIONS = 2

_QUANT_INSTRUCTION = (
    "You are a quantitative analyst. Use the provided pandas REPL tool to "
    "compute an EXACT answer to the user's question from the pre-loaded "
    "DataFrames. Write a single block of pandas code that prints the result. "
    "Do not estimate — always run the tool."
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
    return found


def _parse_planner_output(raw: str) -> tuple[str, str]:
    """Parse the planner's ``QUERY:`` / ``ROUTE:`` reply into (query, route)."""
    query, route = "", "direct_answer"
    for line in raw.splitlines():
        stripped = line.strip()
        upper = stripped.upper()
        if upper.startswith("QUERY:"):
            query = stripped[6:].strip()
        elif upper.startswith("ROUTE:"):
            value = stripped[6:].strip().lower()
            if "pandas_calc" in value:
                route = "pandas_calc"
            elif "vector_search" in value:
                route = "vector_search"
            else:
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
    history = list(state["messages"])  # prior turns + the current question
    response = _get_llm().invoke([SystemMessage(content=QUERY_PLANNER_PROMPT)] + history)
    resolved_query, route = _parse_planner_output(extract_text(response))

    if not resolved_query:
        # Planner did not echo a QUERY line — fall back to the raw question.
        resolved_query = _last_user_message(state)

    intent = {
        "vector_search": "narrative",
        "pandas_calc": "quantitative",
    }.get(route, "chat")

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
    """Track B — compute an exact answer via the pandas REPL tool."""
    query = state.get("resolved_query") or _last_user_message(state)
    tool = _get_pandas_tool()
    llm_with_tool = _get_llm().bind_tools([tool])

    ai_message = llm_with_tool.invoke(
        [SystemMessage(content=_QUANT_INSTRUCTION), HumanMessage(content=query)]
    )

    if not ai_message.tool_calls:
        # No code generated — fall back to the model's direct text.
        logger.warning("Quantitative node: model returned no tool call.")
        return {"context": extract_text(ai_message), "sources": []}

    results: list[str] = []
    code_blocks: list[str] = []
    for call in ai_message.tool_calls:
        code = call["args"]
        code_text = code.get("query", "") if isinstance(code, dict) else str(code)
        code_blocks.append(code_text)
        try:
            output = tool.invoke(code)
        except Exception as exc:  # noqa: BLE001 - surface REPL errors as context
            output = f"Pandas execution error: {exc}"
        results.append(f"Code:\n{code_text}\n\nResult:\n{output}")

    context = "\n\n".join(results)

    # Cite the data file(s) the generated code actually referenced.
    all_code = " ".join(code_blocks)
    sources: list[str] = []
    if "stock_df" in all_code:
        sources.append(STOCK_CSV)
    if "investor_df" in all_code:
        sources.append(INVESTOR_XLS)
    if not sources:
        sources = [STOCK_CSV, INVESTOR_XLS]

    logger.info("Quantitative node produced %d chars of context.", len(context))
    return {"context": context, "sources": sources}


def drafter_node(state: FinancialAgentState) -> dict[str, Any]:
    """Synthesise the analyst answer from the assembled context.

    Writes to ``draft`` (not ``messages``) so redraft cycles never pollute the
    conversation history.
    """
    context = state.get("context") or "(no supporting evidence was retrieved)"
    errors = state.get("errors") or ""

    # System prompt + the full conversation. The message list ends on the
    # current human turn, so the model always has something to answer.
    llm_messages: list = [
        SystemMessage(content=ANALYST_DRAFTER_PROMPT.format(context=context))
    ]
    llm_messages += list(state["messages"])

    if errors:
        # On a redraft, hand back the rejected draft plus the Critic's feedback.
        llm_messages.append(
            HumanMessage(
                content="Your previous draft failed fact-check. Correct these "
                f"specific issues and write the full answer again.\n\n"
                f"ISSUES:\n{errors}\n\nPREVIOUS DRAFT:\n{state.get('draft', '')}"
            )
        )

    response = _get_llm().invoke(llm_messages)
    draft = extract_text(response)
    revisions = state.get("revisions", 0) + 1
    logger.info("Drafter produced draft #%d (%d chars).", revisions, len(draft))
    return {"draft": draft, "revisions": revisions}


def critic_node(state: FinancialAgentState) -> dict[str, Any]:
    """Fact-check the working draft against the context.

    Writes a non-empty ``errors`` string on failure (triggering a redraft) or
    clears it on success.
    """
    context = state.get("context") or ""
    draft = state.get("draft", "")

    # Nothing to verify against (e.g. general chat) — accept the draft.
    if not context:
        return {"errors": ""}

    # Gemini requires at least one non-system content message, so the audit
    # instruction is delivered as a HumanMessage alongside the system prompt.
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

    if verdict.upper().startswith("PASS"):
        logger.info("Critic: draft PASSED fact-check.")
        return {"errors": ""}

    logger.warning("Critic: draft FAILED fact-check — %s", verdict)
    return {"errors": verdict}


def format_node(state: FinancialAgentState) -> dict[str, Any]:
    """Choose the delivery format and finalise the answer.

    Picks ``pdf`` or ``excel`` based on the answer's nature (every answer is
    delivered as a downloadable file) and appends the final answer to
    ``messages`` as this turn's assistant reply.
    """
    question = state.get("resolved_query") or _last_user_message(state)
    answer = state.get("draft") or "I could not produce an answer."

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
        "messages": [AIMessage(content=answer)],
    }
