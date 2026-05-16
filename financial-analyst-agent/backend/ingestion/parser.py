"""PDF extraction via LlamaParse.

Infosys IFRS press releases and the annual report contain dense P&L, balance
sheet, and cash-flow tables. Standard text extractors (PyPDF) collapse these
into unreadable token streams. LlamaParse is configured to emit GitHub-flavored
Markdown so that table structure — row/column headers, fiscal periods, currency
units — survives into the chunking stage intact.
"""

from __future__ import annotations

import logging
from pathlib import Path

from llama_parse import LlamaParse

from backend.core.config import get_settings

logger = logging.getLogger(__name__)

# Domain-specific guidance steers LlamaParse toward faithful table reproduction
# instead of prose summarisation.
_PARSING_INSTRUCTION = (
    "This is an Infosys IFRS financial document (an annual report or a "
    "quarterly earnings press release). Reproduce every financial table "
    "exactly as a GitHub-flavored Markdown table, preserving all row and "
    "column headers, fiscal periods, currency units, and signs. Do not "
    "summarise, round, reorder, or omit any numeric values."
)


def extract_financial_pdf(file_path: str) -> str:
    """Extract a financial PDF into table-preserving Markdown.

    Args:
        file_path: Absolute or relative path to the source PDF.

    Returns:
        The full document rendered as Markdown, with one section per page
        joined by blank lines.

    Raises:
        FileNotFoundError: If ``file_path`` does not point to an existing file.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"PDF not found: {path}")

    settings = get_settings()
    parser = LlamaParse(
        api_key=settings.LLAMA_CLOUD_API_KEY,
        result_type="markdown",
        parsing_instruction=_PARSING_INSTRUCTION,
        verbose=True,
    )

    logger.info("Parsing %s with LlamaParse...", path.name)
    documents = parser.load_data(str(path))
    markdown = "\n\n".join(doc.text for doc in documents if doc.text)
    logger.info("Extracted %d characters of Markdown from %s.", len(markdown), path.name)
    return markdown
