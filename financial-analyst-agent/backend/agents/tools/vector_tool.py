"""Vector search tool — Track A (narrative retrieval).

Wraps the Sprint 1 :class:`ChromaFinancialRetriever` so the agent can pull
narrative context out of the indexed PDF corpus.

Retrieval is quarter-aware:
- No quarter referenced  -> one unfiltered re-ranked search.
- One quarter referenced -> one search filtered to that quarter.
- Several quarters (a comparison) -> one filtered search PER quarter, merged,
  so every quarter is guaranteed to be represented in the context. A single
  filter would otherwise restrict the whole answer to just one quarter.

Retrieval also exposes the *source documents* it drew from, so the agent can
cite every document deterministically rather than relying on the LLM.
"""

from __future__ import annotations

import logging

from langchain_core.documents import Document
from langchain_core.tools import tool

from backend.database.chroma_client import ChromaFinancialRetriever

logger = logging.getLogger(__name__)

# The retriever loads a local embedding model, so it is built once and reused
# across every tool call rather than re-instantiated each time.
_retriever: ChromaFinancialRetriever | None = None

# Chunks delivered for a single-quarter / no-quarter search. The retriever
# fetches a wide candidate pool internally and re-ranks down to this few.
_TOP_K = 7

# Chunks delivered PER quarter in a multi-quarter comparison. Kept smaller so a
# four-quarter comparison stays a reasonable context size (4 x 4 = 16 chunks).
_PER_QUARTER_K = 4

# Chunks shorter than this are bare section headers / page numbers — drop them
# so they do not crowd out real content in the context window.
_MIN_CHUNK_CHARS = 40


def _get_retriever() -> ChromaFinancialRetriever:
    """Return the lazily-initialised, process-wide retriever singleton."""
    global _retriever
    if _retriever is None:
        _retriever = ChromaFinancialRetriever()
    return _retriever


def _normalise_quarter(quarter: str | None) -> str | None:
    """Coerce a quarter argument to the indexed ``Q1``–``Q4`` form, or None."""
    if not quarter:
        return None
    digits = "".join(ch for ch in quarter if ch.isdigit())
    if digits in {"1", "2", "3", "4"}:
        return f"Q{digits}"
    return None


def _retrieve_single(query: str, quarter: str | None, k: int) -> list[Document]:
    """Run one filtered, re-ranked retrieval and drop bare-header chunks."""
    filters = {"quarter": quarter} if quarter else None
    documents = _get_retriever().get_context(query=query, filters=filters, k=k)
    return [d for d in documents if len(d.page_content.strip()) >= _MIN_CHUNK_CHARS]


def _retrieve(query: str, quarters: list[str]) -> list[Document]:
    """Retrieve evidence, fanning out per quarter for multi-quarter queries."""
    normalised = [q for q in (_normalise_quarter(q) for q in quarters) if q]
    # De-duplicate while preserving order.
    normalised = list(dict.fromkeys(normalised))

    if len(normalised) >= 2:
        logger.info("Vector search: query=%r quarters=%s (per-quarter)", query, normalised)
        merged: list[Document] = []
        for quarter in normalised:
            merged.extend(_retrieve_single(query, quarter, _PER_QUARTER_K))
        return merged

    quarter = normalised[0] if normalised else None
    logger.info("Vector search: query=%r quarter=%s", query, quarter)
    return _retrieve_single(query, quarter, _TOP_K)


def format_evidence(documents: list[Document]) -> str:
    """Render retrieved documents into a single cited context block."""
    if not documents:
        return "No substantive content found in the Infosys documents for this query."
    blocks: list[str] = []
    for doc in documents:
        source = doc.metadata.get("source", "unknown")
        section = doc.metadata.get("header_1") or doc.metadata.get("header_2") or "—"
        blocks.append(f"[Source: {source} | Section: {section}]\n{doc.page_content}")
    return "\n\n---\n\n".join(blocks)


def collect_sources(documents: list[Document]) -> list[str]:
    """Return the unique source document names, in first-seen order."""
    ordered: dict[str, None] = {}
    for doc in documents:
        source = doc.metadata.get("source")
        if source:
            ordered.setdefault(source, None)
    return list(ordered)


def search_financial_context(
    query: str, quarters: list[str] | None = None
) -> tuple[str, list[str]]:
    """Retrieve evidence and the list of source documents it was drawn from.

    Args:
        query: The natural-language search string.
        quarters: Fiscal quarters referenced by the query (``"Q1"``–``"Q4"``).
            Two or more triggers a per-quarter retrieval so a comparison sees
            every quarter; one scopes the search; empty searches everything.

    Returns:
        A ``(context, sources)`` tuple — the formatted evidence block and the
        unique source document names backing it.
    """
    documents = _retrieve(query, quarters or [])
    return format_evidence(documents), collect_sources(documents)


@tool
def search_financial_docs(
    query: str,
    quarter: str | None = None,
    year: str | None = None,
) -> str:
    """Search Infosys financial documents for narrative/qualitative information.

    Use this for strategy, management commentary, guidance, segment narratives,
    and any qualitative question — NOT for exact spreadsheet math.

    Args:
        query: The natural-language search string.
        quarter: Optional fiscal quarter filter (``"Q1"``–``"Q4"``). When given,
            results are restricted to that quarter's press release.
        year: Optional fiscal year. The current corpus is entirely Infosys FY26,
            so this is informational only and is not used as a filter.

    Returns:
        The concatenated text of the most relevant document chunks, each
        prefixed with its source and page/section metadata for citation.
    """
    context, _ = search_financial_context(query, [quarter] if quarter else None)
    return context
