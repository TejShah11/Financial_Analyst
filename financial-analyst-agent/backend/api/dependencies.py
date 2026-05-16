"""FastAPI dependency providers.

The LangGraph agent is compiled exactly once at import time. ``get_agent`` hands
that singleton to endpoints via FastAPI's dependency-injection system, so no
graph is rebuilt per request.
"""

from __future__ import annotations

from backend.agents.graph import app as _compiled_agent


def get_agent():
    """Return the process-wide compiled LangGraph agent."""
    return _compiled_agent
