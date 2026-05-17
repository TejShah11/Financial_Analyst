"""LangGraph DAG definition for the financial-analyst agent.

Wires the agent nodes into a directed graph:

    query_planner ─┬─(narrative)────► retrieval ─────┐
                   ├─(quantitative)─► quantitative ──┤
                   └─(chat)─────────────────────────►├─► drafter ─► critic ─┬─(errors)─► drafter
                                                      ┘                     └─(ok)──► format ─► END

The ``format`` node decides the delivery format (text / pdf / excel) for the
finished answer. The compiled graph is exported as ``app``.
"""

from __future__ import annotations

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


def _route_after_planner(state: FinancialAgentState) -> str:
    """Branch out of the planner based on the classified intent."""
    intent = state.get("intent", "chat")
    if intent == "narrative":
        return "retrieval"
    if intent == "quantitative":
        return "quantitative"
    # "chat" / anything else answers directly with no evidence-gathering step.
    return "drafter"


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

    # Planner routes to one of the three evidence paths.
    workflow.add_conditional_edges(
        "query_planner",
        _route_after_planner,
        {
            "retrieval": "retrieval",
            "quantitative": "quantitative",
            "drafter": "drafter",
        },
    )

    # Both evidence-gathering tracks converge on the Drafter.
    workflow.add_edge("retrieval", "drafter")
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


# Compiled graph — the public entry point used by the API and test scripts.
app = build_graph().compile()
