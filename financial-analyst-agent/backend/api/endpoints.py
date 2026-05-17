"""API routes for the financial analyst service.

Exposes the LangGraph agent over HTTP and serves generated Excel/PDF artifacts.

- ``POST /chat``         — run the agent, return the answer + a downloadable file.
- ``POST /chat/stream``  — same, but streams node-by-node progress as NDJSON.
- ``GET  /history/{id}`` — replay a conversation thread (survives UI refresh).
- ``GET  /download/...`` — serve a generated artifact.

Multi-turn memory is keyed by ``session_id`` (the LangGraph thread id); the
output format (PDF / Excel) is chosen by the agent's format node.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Iterator
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from langchain_core.messages import HumanMessage

from backend.agents.nodes import extract_text
from backend.api.dependencies import get_agent
from backend.api.schemas import ChatRequest, ChatResponse
from backend.core.config import get_settings
from backend.utils.excel_generator import generate_excel
from backend.utils.pdf_generator import generate_pdf_report

logger = logging.getLogger(__name__)

router = APIRouter()

# Human-readable labels for each graph node, surfaced to the UI as progress.
NODE_LABELS: dict[str, str] = {
    "query_planner": "Understanding the question and resolving follow-ups...",
    "retrieval": "Searching the financial documents...",
    "quantitative": "Running calculations on the data...",
    "drafter": "Drafting the analysis...",
    "critic": "Fact-checking the answer against the sources...",
    "format": "Selecting the best output format...",
}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _is_separator(cells: list[str]) -> bool:
    """True if a parsed table row is the Markdown header separator (|---|---|)."""
    return all(set(cell) <= set("-: ") and cell for cell in cells)


def _extract_tables(text: str) -> list[list[dict]]:
    """Parse EVERY Markdown table in ``text`` into a list of record-lists."""
    tables: list[list[dict]] = []
    block: list[list[str]] = []

    def _flush() -> None:
        if len(block) >= 2:
            header = block[0]
            records = [
                dict(zip(header, row))
                for row in block[1:]
                if not _is_separator(row) and len(row) == len(header)
            ]
            if records:
                tables.append(records)
        block.clear()

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            block.append([c.strip() for c in stripped.strip("|").split("|")])
        else:
            _flush()
    _flush()
    return tables


def _fresh_turn_input(query: str) -> dict:
    """Graph input for a new turn.

    ``messages`` is appended by the checkpointer's reducer (preserving history);
    every other field is reset so a new turn does not inherit stale per-turn
    state (e.g. a leftover revision count or the previous answer's draft).
    """
    return {
        "messages": [("user", query)],
        "resolved_query": "",
        "context": "",
        "intent": "",
        "draft": "",
        "errors": "",
        "revisions": 0,
        "sources": [],
        "output_format": "",
        "verified": True,
    }


def _generate_artifact(answer: str, output_format: str) -> str:
    """Render the answer to a PDF/Excel file and return its download URL.

    For Excel, EVERY Markdown table in the answer is exported — multiple tables
    become multiple sheets so none is silently dropped.
    """
    suffix = uuid.uuid4().hex[:8]
    if output_format == "excel":
        tables = _extract_tables(answer)
        if len(tables) > 1:
            data: list[dict] | dict[str, list[dict]] = {
                f"Table {i}": table for i, table in enumerate(tables, start=1)
            }
        elif len(tables) == 1:
            data = tables[0]
        else:
            data = [{"response": answer}]
        path = generate_excel(data, filename=f"analysis_{suffix}.xlsx")
    else:
        path = generate_pdf_report(answer, filename=f"report_{suffix}.pdf")
    return f"/download/{Path(path).name}"


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest, agent=Depends(get_agent)) -> ChatResponse:
    """Run the agent for a query and return the answer + a downloadable file."""
    thread_id = request.session_id or uuid.uuid4().hex
    config = {"configurable": {"thread_id": thread_id}}

    try:
        result = agent.invoke(_fresh_turn_input(request.query), config=config)
    except Exception as exc:  # noqa: BLE001 - convert any agent failure to HTTP
        logger.exception("Agent invocation failed.")
        raise HTTPException(
            status_code=502, detail=f"Agent execution failed: {exc}"
        ) from exc

    answer = result.get("draft") or "(no answer produced)"
    output_format = result.get("output_format") or "pdf"
    file_url = _generate_artifact(answer, output_format)

    return ChatResponse(
        answer=answer,
        intent=result.get("intent", "chat"),
        sources=result.get("sources", []),
        verified=result.get("verified", True),
        file_url=file_url,
    )


@router.post("/chat/stream")
def chat_stream(request: ChatRequest, agent=Depends(get_agent)) -> StreamingResponse:
    """Run the agent and stream node-by-node progress, then the final result.

    Emits newline-delimited JSON: a ``progress`` event per graph node, then a
    single ``result`` event (or an ``error`` event on failure).
    """
    thread_id = request.session_id or uuid.uuid4().hex
    config = {"configurable": {"thread_id": thread_id}}

    def _events() -> Iterator[str]:
        try:
            for chunk in agent.stream(
                _fresh_turn_input(request.query), config=config, stream_mode="updates"
            ):
                for node in chunk:
                    yield json.dumps(
                        {
                            "type": "progress",
                            "node": node,
                            "label": NODE_LABELS.get(node, node),
                        }
                    ) + "\n"

            final = agent.get_state(config).values
            answer = final.get("draft") or "(no answer produced)"
            output_format = final.get("output_format") or "pdf"

            yield json.dumps(
                {
                    "type": "progress",
                    "node": "file",
                    "label": f"Generating {output_format.upper()} file...",
                }
            ) + "\n"
            file_url = _generate_artifact(answer, output_format)

            yield json.dumps(
                {
                    "type": "result",
                    "answer": answer,
                    "intent": final.get("intent", "chat"),
                    "sources": final.get("sources", []),
                    "verified": final.get("verified", True),
                    "file_url": file_url,
                }
            ) + "\n"
        except Exception as exc:  # noqa: BLE001 - stream the failure to the client
            logger.exception("Streaming agent run failed.")
            yield json.dumps(
                {"type": "error", "detail": f"Agent execution failed: {exc}"}
            ) + "\n"

    return StreamingResponse(_events(), media_type="application/x-ndjson")


@router.get("/history/{session_id}")
def history(session_id: str, agent=Depends(get_agent)) -> dict:
    """Replay a conversation thread so the UI can restore it after a refresh."""
    config = {"configurable": {"thread_id": session_id}}
    try:
        state_values = agent.get_state(config).values or {}
    except Exception:  # noqa: BLE001 - an unknown thread is simply empty
        return {"messages": []}

    messages = []
    for message in state_values.get("messages", []):
        role = "user" if isinstance(message, HumanMessage) else "assistant"
        messages.append({"role": role, "content": extract_text(message)})
    return {"messages": messages}


@router.get("/download/{filename}")
def download(filename: str) -> FileResponse:
    """Serve a previously generated artifact from the exports directory."""
    # Path(...).name strips any traversal segments (e.g. ../../etc/passwd).
    safe_name = Path(filename).name
    file_path = get_settings().EXPORTS_DIR / safe_name

    if not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {safe_name}")

    return FileResponse(path=str(file_path.resolve()), filename=safe_name)
