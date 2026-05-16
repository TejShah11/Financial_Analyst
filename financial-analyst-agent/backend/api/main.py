"""FastAPI application entry point for the financial analyst backend.

Run with:  uv run uvicorn backend.api.main:app --reload
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.endpoints import router

app = FastAPI(
    title="LedgerMind Core API",
    version="1.0.0",
    description="Agentic financial analyst backend (LangGraph + ChromaDB + Gemini).",
)

# CORS — open for local development so the Streamlit UI can call the API.
# allow_credentials stays False because a wildcard origin with credentials is
# rejected by browsers; the UI does not send cookies.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "healthy"}
