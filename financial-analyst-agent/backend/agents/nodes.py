"""LangGraph node functions for the financial-analyst DAG.

Each node receives the :class:`FinancialAgentState` and returns a *partial*
update dict, which LangGraph merges back into the state. The graph wiring lives
in ``graph.py``; this module only implements per-node behaviour.
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
    ROUTER_PROMPT,
)
from backend.agents.state import FinancialAgentState
from backend.agents.tools.pandas_tool import get_tabular_tool
from backend.agents.tools.vector_tool import search_financial_docs
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
# State helpers
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
            return str(message.content)
    return ""


def _last_ai_message(state: FinancialAgentState) -> str:
    """Return the text of the most recent AI draft, or '' if none."""
    for message in reversed(state["messages"]):
        if isinstance(message, AIMessage):
            return extract_text(message)
    return ""


def _extract_quarter(text: str) -> str | None:
    """Detect an explicit fiscal quarter (Q1-Q4) mentioned in the query."""
    match = re.search(r"\bq([1-4])\b", text, flags=re.IGNORECASE)
    return f"Q{match.group(1)}" if match else None


# --------------------------------------------------------------------------- #
# Nodes
# --------------------------------------------------------------------------- #
def query_planner_node(state: FinancialAgentState) -> dict[str, Any]:
    """Classify the latest query and set the routing ``intent``."""
    user_query = _last_user_message(state)
    response = _get_llm().invoke(
        [SystemMessage(content=ROUTER_PROMPT), HumanMessage(content=user_query)]
    )
    raw = extract_text(response).strip().lower()

    if "pandas_calc" in raw:
        intent = "quantitative"
    elif "vector_search" in raw:
        intent = "narrative"
    else:
        intent = "chat"

    logger.info("Router classified query as intent=%s (raw=%r)", intent, raw)
    return {"intent": intent}


def retrieval_node(state: FinancialAgentState) -> dict[str, Any]:
    """Track A — pull narrative context from the vector store."""
    user_query = _last_user_message(state)
    quarter = _extract_quarter(user_query)
    context = search_financial_docs.invoke({"query": user_query, "quarter": quarter})
    logger.info("Retrieval node produced %d chars of context.", len(context))
    return {"context": context}


def quantitative_node(state: FinancialAgentState) -> dict[str, Any]:
    """Track B — compute an exact answer via the pandas REPL tool."""
    user_query = _last_user_message(state)
    tool = _get_pandas_tool()
    llm_with_tool = _get_llm().bind_tools([tool])

    ai_message = llm_with_tool.invoke(
        [SystemMessage(content=_QUANT_INSTRUCTION), HumanMessage(content=user_query)]
    )

    if not ai_message.tool_calls:
        # No code generated — fall back to the model's direct text.
        logger.warning("Quantitative node: model returned no tool call.")
        return {"context": extract_text(ai_message)}

    results: list[str] = []
    for call in ai_message.tool_calls:
        code = call["args"]
        try:
            output = tool.invoke(code)
        except Exception as exc:  # noqa: BLE001 - surface REPL errors as context
            output = f"Pandas execution error: {exc}"
        results.append(f"Code:\n{code.get('query', code)}\n\nResult:\n{output}")

    context = "\n\n".join(results)
    logger.info("Quantitative node produced %d chars of context.", len(context))
    return {"context": context}


def drafter_node(state: FinancialAgentState) -> dict[str, Any]:
    """Synthesise the analyst answer from the assembled context."""
    context = state.get("context") or "(no supporting evidence was retrieved)"
    errors = state.get("errors") or ""

    system_messages = [SystemMessage(content=ANALYST_DRAFTER_PROMPT.format(context=context))]
    if errors:
        # Feed the Critic's feedback back so the rewrite fixes the exact issues.
        system_messages.append(
            SystemMessage(content=f"CRITIC FEEDBACK on your previous draft:\n{errors}")
        )

    response = _get_llm().invoke(system_messages + list(state["messages"]))
    revisions = state.get("revisions", 0) + 1
    logger.info("Drafter produced draft #%d.", revisions)
    return {"messages": [response], "revisions": revisions}


def critic_node(state: FinancialAgentState) -> dict[str, Any]:
    """Fact-check the latest draft against the context.

    Writes a non-empty ``errors`` string on failure (triggering a redraft) or
    clears it on success.
    """
    context = state.get("context") or ""
    draft = _last_ai_message(state)

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
