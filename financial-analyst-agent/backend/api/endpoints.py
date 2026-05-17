"""API routes for the financial analyst service.

Exposes the LangGraph agent over HTTP and serves generated Excel/PDF artifacts.
The output format is chosen by the agent's ``format`` node — never by parsing
the user's wording — so the system, not the user, decides the delivery format.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from backend.agents.nodes import extract_text
from backend.api.dependencies import get_agent
from backend.api.schemas import ChatRequest, ChatResponse
from backend.core.config import get_settings
from backend.utils.excel_generator import generate_excel
from backend.utils.pdf_generator import generate_pdf_report

logger = logging.getLogger(__name__)

router = APIRouter()


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


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest, agent=Depends(get_agent)) -> ChatResponse:
    """Run the agent for a query and deliver the answer in the chosen format."""
    try:
        result = agent.invoke({"messages": [("user", request.query)]})
    except Exception as exc:  # noqa: BLE001 - convert any agent failure to HTTP
        logger.exception("Agent invocation failed.")
        raise HTTPException(
            status_code=502, detail=f"Agent execution failed: {exc}"
        ) from exc

    messages = result.get("messages", [])
    answer = extract_text(messages[-1]) if messages else "(no answer produced)"
    intent = result.get("intent", "chat")
    sources = result.get("sources", [])
    # The agent's format node decides text / pdf / excel — not the user.
    output_format = result.get("output_format", "text")

    file_url: str | None = None
    if output_format == "excel":
        records = _extract_table_records(answer) or [{"response": answer}]
        path = generate_excel(records, filename="chat_export.xlsx")
        file_url = f"/download/{Path(path).name}"
    elif output_format == "pdf":
        path = generate_pdf_report(answer, filename="chat_report.pdf")
        file_url = f"/download/{Path(path).name}"

    return ChatResponse(
        answer=answer, intent=intent, sources=sources, file_url=file_url
    )


@router.get("/download/{filename}")
def download(filename: str) -> FileResponse:
    """Serve a previously generated artifact from the exports directory."""
    # Path(...).name strips any traversal segments (e.g. ../../etc/passwd).
    safe_name = Path(filename).name
    file_path = get_settings().EXPORTS_DIR / safe_name

    if not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {safe_name}")

    return FileResponse(path=str(file_path.resolve()), filename=safe_name)
