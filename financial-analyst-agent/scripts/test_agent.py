"""Manual smoke test for the Sprint 2 LangGraph agent.

Streams the graph state node-by-node so the routing, retrieval, drafting and
critic stages are visible in real time.

Run from anywhere:  uv run python scripts/test_agent.py
"""

from __future__ import annotations

import logging
import sys
import uuid
from pathlib import Path

# Make the project package importable when run as a plain script.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Financial text contains ₹, em-dashes, etc.; force UTF-8 so the default
# Windows cp1252 console does not raise UnicodeEncodeError on print().
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402

from backend.agents.graph import app  # noqa: E402
from backend.agents.nodes import extract_text  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-7s | %(name)s | %(message)s",
)

DEFAULT_QUERY = "What was the operating margin in Q4 FY26?"


def _resolve_query() -> str:
    """Use a question passed on the command line, else the default query."""
    if len(sys.argv) > 1:
        return " ".join(sys.argv[1:]).strip()
    return DEFAULT_QUERY


def _preview(value: object, limit: int = 600) -> str:
    """Trim a value to a readable single-block preview."""
    text = str(value).replace("\n", "\n    ")
    return text if len(text) <= limit else text[:limit] + " ...(truncated)"


def main() -> None:
    """Stream the graph for the test query and print each node's output."""
    query = _resolve_query()
    print("=" * 70)
    print(f"QUERY: {query}")
    print("=" * 70)

    initial_state = {
        "messages": [HumanMessage(content=query)],
        "resolved_query": "",
        "context": "",
        "intent": "",
        "draft": "",
        "errors": "",
        "revisions": 0,
        "sources": [],
        "output_format": "",
    }

    final_answer = "(no answer produced)"

    # The compiled graph uses a checkpointer, so a thread id is required.
    config = {"configurable": {"thread_id": f"test-{uuid.uuid4().hex[:8]}"}}

    # stream_mode="updates" yields {node_name: partial_state_update} per step.
    for step in app.stream(initial_state, config=config, stream_mode="updates"):
        for node_name, update in step.items():
            print(f"\n---------- NODE: {node_name} ----------")
            for key, value in update.items():
                if key == "messages":
                    for message in value:
                        text = extract_text(message)
                        if isinstance(message, AIMessage):
                            final_answer = text
                        print(f"  messages += [{type(message).__name__}]")
                        print(f"    {_preview(text)}")
                else:
                    print(f"  {key}: {_preview(value)}")

    print("\n" + "=" * 70)
    print("FINAL ANSWER:")
    print("=" * 70)
    print(final_answer)


if __name__ == "__main__":
    main()
