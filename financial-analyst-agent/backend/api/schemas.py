"""Pydantic request/response models for the API layer.

These schemas are the strict contract between the FastAPI endpoints and any
client (the Streamlit UI, Swagger, external callers).
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Inbound payload for the ``POST /chat`` endpoint."""

    query: str = Field(
        ...,
        min_length=1,
        description="The user's natural-language financial question.",
    )


class ChatResponse(BaseModel):
    """Outbound payload returned by the ``POST /chat`` endpoint."""

    answer: str = Field(
        ..., description="The analyst's text answer (may contain a Markdown table)."
    )
    intent: str = Field(
        ..., description="Routing/output intent resolved for this turn."
    )
    file_url: Optional[str] = Field(
        default=None,
        description="Relative download URL when an Excel/PDF artifact was generated.",
    )
