"""LangGraph DAG definition for the financial-analyst agent.

Wires the agent nodes into a directed graph:

    query_planner ─┬─(narrative)────► retrieval ─────────────────┐
                   ├─(hybrid)───────► retrieval ─► quantitative ─┤
                   ├─(quantitative)─► quantitative ──────────────┤
                   └─(chat)──────────────────────────────────────┤
                                                                  ▼
                       drafter ─► critic ─┬─(errors)─► drafter
                                          └─(ok)─────► format ─► END

A *hybrid* question routes through BOTH retrieval and the quantitative track;
the quantitative node appends its computed result to the retrieved context so
the drafter can answer from combined evidence.

Conversation state is persisted with a SqliteSaver checkpointer, so multi-turn
memory survives server restarts. The compiled graph is exported as ``app``.
"""

from __future__ import annotations

import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph

from backend.agents.nodes import (
    MAX_REVISIONS,
    critic_node,
    drafter_node,
    format_node,
    quantitative_node,
    query_planner_node,
    retrieval_node,
)
from backend.agents.state import FinancialAgentState
from backend.core.config import get_settings


def _route_after_planner(state: FinancialAgentState) -> str:
    """Branch out of the planner based on the classified intent."""
    intent = state.get("intent", "chat")
    if intent in ("narrative", "hybrid"):
        # Hybrid questions gather narrative evidence first, then compute.
        return "retrieval"
    if intent == "quantitative":
        return "quantitative"
    # "chat" answers directly with no evidence-gathering step.
    return "drafter"


def _route_after_retrieval(state: FinancialAgentState) -> str:
    """After retrieval, a hybrid query also runs the quantitative track."""
    return "quantitative" if state.get("intent") == "hybrid" else "drafter"


def _route_after_critic(state: FinancialAgentState) -> str:
    """Loop back to the Drafter on a failed fact-check, else move to formatting.

    The ``revisions`` guard ensures a persistently failing draft cannot trigger
    an unbounded Drafter <-> Critic cycle.
    """
    has_errors = bool(state.get("errors"))
    revisions = state.get("revisions", 0)
    if has_errors and revisions < MAX_REVISIONS:
        return "drafter"
    return "format"


def build_graph() -> StateGraph:
    """Construct and return the (uncompiled) financial-analyst state graph."""
    workflow = StateGraph(FinancialAgentState)

    # --- Nodes -------------------------------------------------------------- #
    workflow.add_node("query_planner", query_planner_node)
    workflow.add_node("retrieval", retrieval_node)
    workflow.add_node("quantitative", quantitative_node)
    workflow.add_node("drafter", drafter_node)
    workflow.add_node("critic", critic_node)
    workflow.add_node("format", format_node)

    # --- Edges -------------------------------------------------------------- #
    workflow.set_entry_point("query_planner")

    workflow.add_conditional_edges(
        "query_planner",
        _route_after_planner,
        {
            "retrieval": "retrieval",
            "quantitative": "quantitative",
            "drafter": "drafter",
        },
    )

    # Retrieval continues to the quantitative track for hybrid queries.
    workflow.add_conditional_edges(
        "retrieval",
        _route_after_retrieval,
        {"quantitative": "quantitative", "drafter": "drafter"},
    )
    workflow.add_edge("quantitative", "drafter")

    # Every draft is fact-checked.
    workflow.add_edge("drafter", "critic")

    # Critic either sends the draft back for a rewrite or passes it to the
    # format node, which chooses the delivery format before the run ends.
    workflow.add_conditional_edges(
        "critic",
        _route_after_critic,
        {"drafter": "drafter", "format": "format"},
    )
    workflow.add_edge("format", END)

    return workflow


def _build_checkpointer() -> SqliteSaver:
    """Build a disk-backed checkpointer so memory survives server restarts."""
    db_path = get_settings().CHECKPOINT_DB
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: uvicorn serves requests across worker threads
    # that all share this single connection.
    connection = sqlite3.connect(str(db_path), check_same_thread=False)
    checkpointer = SqliteSaver(connection)
    checkpointer.setup()  # idempotent — creates the checkpoint tables if absent.
    return checkpointer


# Compiled graph — the public entry point used by the API and test scripts.
# Callers must pass config={"configurable": {"thread_id": ...}} on every run.
app = build_graph().compile(checkpointer=_build_checkpointer())
