"""Pydantic request/response models for the API layer.

These schemas are the strict contract between the FastAPI endpoints and any
client (the Streamlit UI, Swagger, external callers).
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Inbound payload for the ``POST /chat`` and ``/chat/stream`` endpoints."""

    query: str = Field(
        ...,
        min_length=1,
        description="The user's natural-language financial question.",
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Conversation thread id. Send the same value across turns "
        "to give the agent multi-turn memory; omit it for a stateless one-off.",
    )


class ChatResponse(BaseModel):
    """Outbound payload returned by the ``POST /chat`` endpoint."""

    answer: str = Field(
        ..., description="The analyst's text answer (may contain a Markdown table)."
    )
    intent: str = Field(
        ..., description="Routing intent resolved for this turn."
    )
    sources: list[str] = Field(
        default_factory=list,
        description="Document(s) every piece of evidence for this answer was "
        "drawn from — the citation guarantee.",
    )
    file_url: Optional[str] = Field(
        default=None,
        description="Relative download URL when an Excel/PDF artifact was generated.",
    )
