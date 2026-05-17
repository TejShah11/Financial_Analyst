"""API routes for the financial analyst service.

Exposes the LangGraph agent over HTTP and serves generated Excel/PDF artifacts.

- ``POST /chat``        — run the agent, return the answer + a downloadable file.
- ``POST /chat/stream`` — same, but streams node-by-node progress as NDJSON so
  the UI can show what the backend is doing in real time.
- ``GET  /download/...``— serve a generated artifact.

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


def _extract_table_records(text: str) -> list[dict]:
    """Parse the first Markdown table in ``text`` into a list of row dicts."""
    rows = [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in text.splitlines()
        if line.strip().startswith("|") and line.strip().endswith("|")
    ]
    if len(rows) < 2:
        return []

    header = rows[0]
    records: list[dict] = []
    for row in rows[1:]:
        if _is_separator(row) or len(row) != len(header):
            continue
        records.append(dict(zip(header, row)))
    return records


def _fresh_turn_input(query: str) -> dict:
    """Graph input for a new turn.

    ``messages`` is appended by the checkpointer's reducer (preserving history);
    every other field is reset so a new turn does not inherit stale per-turn
    state (e.g. a leftover revision count).
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
    }


def _generate_artifact(answer: str, output_format: str) -> str:
    """Render the answer to a PDF/Excel file and return its download URL."""
    suffix = uuid.uuid4().hex[:8]
    if output_format == "excel":
        records = _extract_table_records(answer) or [{"response": answer}]
        path = generate_excel(records, filename=f"analysis_{suffix}.xlsx")
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
                    "file_url": file_url,
                }
            ) + "\n"
        except Exception as exc:  # noqa: BLE001 - stream the failure to the client
            logger.exception("Streaming agent run failed.")
            yield json.dumps(
                {"type": "error", "detail": f"Agent execution failed: {exc}"}
            ) + "\n"

    return StreamingResponse(_events(), media_type="application/x-ndjson")


@router.get("/download/{filename}")
def download(filename: str) -> FileResponse:
    """Serve a previously generated artifact from the exports directory."""
    # Path(...).name strips any traversal segments (e.g. ../../etc/passwd).
    safe_name = Path(filename).name
    file_path = get_settings().EXPORTS_DIR / safe_name

    if not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {safe_name}")

    return FileResponse(path=str(file_path.resolve()), filename=safe_name)
