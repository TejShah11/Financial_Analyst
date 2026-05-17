"""LangGraph conversational state for the financial analyst agent.

The state is the single object threaded through every node of the graph. Each
node receives it, returns a partial update, and LangGraph merges the result.

Multi-turn memory is provided by a checkpointer (see ``graph.py``): ``messages``
persists across turns for a given thread, while the per-turn working fields
(``context``, ``draft``, ``errors`` …) are reset on every new request.
"""

from __future__ import annotations

from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class FinancialAgentState(TypedDict):
    """Shared state for the financial-analyst DAG.

    Attributes:
        messages: Conversation history — alternating human questions and final
            assistant answers only (never intermediate drafts). The
            ``add_messages`` reducer appends, so with a checkpointer this
            accumulates across turns and powers follow-up resolution.
        resolved_query: The current question rewritten by the planner into a
            fully self-contained form (pronouns / references resolved against
            the conversation). Retrieval and analysis use this, not the raw text.
        context: Evidence assembled for the current turn — retrieved document
            text (vector search) or computed output (pandas REPL).
        intent: Routing decision from the query planner — one of
            ``"narrative"``, ``"quantitative"`` or ``"chat"``.
        draft: The analyst's working answer for the current turn. The Drafter
            writes it, the Critic checks it; it is kept out of ``messages``
            until finalised so redraft cycles never corrupt the history.
        errors: Feedback written by the Critic when the draft fails fact-check.
            A non-empty value routes the graph back to the Drafter for a rewrite.
        revisions: Number of Critic-triggered redraft cycles so far — a loop
            guard so a persistently failing draft cannot spin forever.
        sources: Deterministic list of document names every piece of evidence
            for this turn was drawn from — the citation guarantee.
        output_format: Delivery format chosen by the format node — ``"pdf"`` or
            ``"excel"`` (every answer is also delivered as a downloadable file).
        verified: Whether the final answer passed the Critic's fact-check. False
            means the revision budget was exhausted with the draft still failing;
            the answer is delivered with an explicit warning.
    """

    messages: Annotated[list, add_messages]
    resolved_query: str
    context: str
    intent: str
    draft: str
    errors: str
    revisions: int
    sources: list[str]
    output_format: str
    verified: bool
