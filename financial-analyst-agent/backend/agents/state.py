"""LangGraph conversational state for the financial analyst agent.

The state is the single object threaded through every node of the graph. Each
node receives it, returns a partial update, and LangGraph merges the result.
"""

from __future__ import annotations

from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class FinancialAgentState(TypedDict):
    """Shared state for the financial-analyst DAG.

    Attributes:
        messages: Full conversation history. The ``add_messages`` reducer
            appends new messages instead of overwriting, preserving multi-turn
            context across nodes.
        context: Evidence assembled for the current turn — retrieved document
            text (vector search) or computed output (pandas REPL). The Drafter
            answers strictly from this field.
        intent: Routing decision from the query planner — one of
            ``"narrative"``, ``"quantitative"``, ``"report"`` or ``"chat"``.
        errors: Feedback written by the Critic when the draft fails fact-check.
            A non-empty value routes the graph back to the Drafter for a rewrite;
            an empty value means the draft passed.
        revisions: Number of Critic-triggered redraft cycles so far. Used purely
            as a loop guard so a persistently failing draft cannot spin forever.
        sources: Deterministic list of document names every piece of evidence
            for this turn was drawn from — the citation guarantee. Populated by
            the retrieval / quantitative nodes, not by the LLM.
        output_format: Delivery format chosen by the format node for this
            answer — one of ``"text"``, ``"pdf"`` or ``"excel"``.
    """

    messages: Annotated[list, add_messages]
    context: str
    intent: str
    errors: str
    revisions: int
    sources: list[str]
    output_format: str
