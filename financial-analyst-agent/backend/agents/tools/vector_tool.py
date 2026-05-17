"""Vector search tool — Track A (narrative retrieval).

Wraps the Sprint 1 :class:`ChromaFinancialRetriever` as a LangChain tool so the
agent can pull narrative context (strategy, commentary, guidance) out of the
indexed PDF corpus, optionally scoped to a specific fiscal quarter.

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

# Final number of chunks delivered to the agent. The retriever fetches a much
# wider candidate pool internally and cross-encoder re-ranks it down to this few,
# so the LLM sees only the most relevant context — no flooding.
_TOP_K = 7

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


def _retrieve(query: str, quarter: str | None) -> list[Document]:
    """Run filtered, re-ranked retrieval and drop bare-header chunks."""
    filters: dict[str, str] | None = None
    normalised = _normalise_quarter(quarter)
    if normalised:
        # Only quarter is indexed as filterable metadata; year is intentionally
        # omitted (single-FY corpus) to avoid producing an empty result set.
        filters = {"quarter": normalised}

    logger.info("Vector search: query=%r quarter=%s", query, normalised)
    documents = _get_retriever().get_context(query=query, filters=filters, k=_TOP_K)
    return [d for d in documents if len(d.page_content.strip()) >= _MIN_CHUNK_CHARS]


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
    query: str, quarter: str | None = None
) -> tuple[str, list[str]]:
    """Retrieve evidence and the list of source documents it was drawn from.

    Returns:
        A ``(context, sources)`` tuple — the formatted evidence block and the
        unique source document names backing it.
    """
    documents = _retrieve(query, quarter)
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
    context, _ = search_financial_context(query, quarter)
    return context
