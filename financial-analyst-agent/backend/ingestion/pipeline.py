"""Master ingestion pipeline: PDF -> Markdown -> chunks -> ChromaDB.

Run with ``uv run python -m backend.ingestion.pipeline``.

The pipeline scans ``data/raw`` for PDFs, extracts each one to Markdown via
LlamaParse, then applies a two-stage Parent-Child split:

  1. ``MarkdownHeaderTextSplitter`` carves the document along ``#`` / ``##``
     headers — the *parent* sections, which keep whole financial tables and
     their surrounding caveats together.
  2. ``RecursiveCharacterTextSplitter`` divides oversized sections into
     embedding-friendly *child* chunks while inheriting the parent's header
     metadata.

Every chunk is tagged with provenance metadata (source file, document type,
and fiscal quarter where derivable) so the retrieval layer can pre-filter on
period for quarter-over-quarter comparisons.
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

from backend.core.config import get_settings
from backend.database.chroma_client import ChromaFinancialRetriever
from backend.ingestion.parser import extract_financial_pdf

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("ingestion.pipeline")

# Parent sections are split on the two top header levels; deeper headers stay
# inside their section so tables are not severed from their titles.
HEADERS_TO_SPLIT_ON = [("#", "header_1"), ("##", "header_2")]

# Child-chunk sizing. ~1k chars keeps embeddings focused while the overlap
# preserves continuity across table/paragraph boundaries.
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150

_QUARTER_RE = re.compile(r"q([1-4])", re.IGNORECASE)


def _derive_metadata(filename: str) -> dict[str, str]:
    """Infer provenance metadata from a raw-document filename.

    Examples:
        ``ifrs-usd-press-release_q2.pdf`` -> press_release / Q2
        ``infosys-ar-25.pdf``            -> annual_report
    """
    stem = filename.lower()
    metadata: dict[str, str] = {"source": filename}

    if "press-release" in stem or "press_release" in stem:
        metadata["doc_type"] = "press_release"
    elif "ar-" in stem or "annual" in stem:
        metadata["doc_type"] = "annual_report"
    else:
        metadata["doc_type"] = "other"

    quarter_match = _QUARTER_RE.search(stem)
    if quarter_match:
        metadata["quarter"] = f"Q{quarter_match.group(1)}"

    return metadata


def chunk_markdown(markdown_text: str, base_metadata: dict[str, str]) -> list[Document]:
    """Apply Parent-Child splitting and attach metadata to every child chunk.

    Args:
        markdown_text: Document Markdown produced by :func:`extract_financial_pdf`.
        base_metadata: Provenance metadata applied to all resulting chunks.

    Returns:
        Embedding-ready child chunks carrying merged provenance + header metadata.
    """
    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=HEADERS_TO_SPLIT_ON,
        strip_headers=False,
    )
    parent_sections = header_splitter.split_text(markdown_text)

    recursive_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )
    child_chunks = recursive_splitter.split_documents(parent_sections)

    # Drop empty / whitespace-only chunks: the embedding API rejects empty
    # content with a 400 INVALID_ARGUMENT ("empty Part") error.
    child_chunks = [c for c in child_chunks if c.page_content.strip()]

    for index, chunk in enumerate(child_chunks):
        # base_metadata wins over any colliding header keys; record chunk order.
        chunk.metadata = {**chunk.metadata, **base_metadata, "chunk_index": index}

    logger.info(
        "Split '%s' into %d parent sections -> %d child chunks.",
        base_metadata.get("source", "<unknown>"),
        len(parent_sections),
        len(child_chunks),
    )
    return child_chunks


def run_pipeline() -> int:
    """Execute the full ingestion pipeline over every PDF in ``data/raw``.

    Returns:
        The total number of chunks indexed into ChromaDB.
    """
    settings = get_settings()
    raw_dir = settings.RAW_DATA_DIR
    processed_dir = settings.PROCESSED_DATA_DIR
    processed_dir.mkdir(parents=True, exist_ok=True)

    pdf_files = sorted(raw_dir.glob("*.pdf"))
    if not pdf_files:
        logger.warning("No PDF files found in %s. Nothing to ingest.", raw_dir)
        return 0

    logger.info("Found %d PDF(s) in %s.", len(pdf_files), raw_dir)
    retriever = ChromaFinancialRetriever()
    total_chunks = 0

    for pdf_path in pdf_files:
        logger.info("=== Ingesting %s ===", pdf_path.name)
        processed_path = processed_dir / f"{pdf_path.stem}.md"

        # Reuse cached Markdown when present: LlamaParse is billed per page, so
        # re-runs (e.g. after an embedding-quota failure) should not re-parse.
        if processed_path.exists() and processed_path.stat().st_size > 0:
            logger.info("Reusing cached Markdown %s (skipping LlamaParse).", processed_path)
            markdown = processed_path.read_text(encoding="utf-8")
        else:
            markdown = extract_financial_pdf(str(pdf_path))
            processed_path.write_text(markdown, encoding="utf-8")
            logger.info("Saved intermediate Markdown to %s.", processed_path)

        chunks = chunk_markdown(markdown, _derive_metadata(pdf_path.name))
        retriever.add_documents(chunks)
        total_chunks += len(chunks)

    logger.info("Ingestion complete: %d chunks indexed from %d PDF(s).",
                total_chunks, len(pdf_files))
    return total_chunks


if __name__ == "__main__":
    try:
        run_pipeline()
    except Exception:  # noqa: BLE001 - surface any failure with a full traceback
        logger.exception("Ingestion pipeline failed.")
        sys.exit(1)
