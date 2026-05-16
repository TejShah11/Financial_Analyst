"""Vector search tool — Track A (narrative retrieval).

Wraps the Sprint 1 :class:`ChromaFinancialRetriever` as a LangChain tool so the
agent can pull narrative context (strategy, commentary, guidance) out of the
indexed PDF corpus, optionally scoped to a specific fiscal quarter.
"""

from __future__ import annotations

import logging

from langchain_core.tools import tool

from backend.database.chroma_client import ChromaFinancialRetriever

logger = logging.getLogger(__name__)

# The retriever loads a local embedding model, so it is built once and reused
# across every tool call rather than re-instantiated each time.
_retriever: ChromaFinancialRetriever | None = None

# Number of chunks returned per search.
_TOP_K = 5


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
    retriever = _get_retriever()

    filters: dict[str, str] | None = None
    normalised = _normalise_quarter(quarter)
    if normalised:
        # Only quarter is indexed as filterable metadata; year is intentionally
        # omitted (single-FY corpus) to avoid producing an empty result set.
        filters = {"quarter": normalised}

    logger.info("Vector search: query=%r quarter=%s", query, normalised)
    documents = retriever.get_context(query=query, filters=filters, k=_TOP_K)

    if not documents:
        return (
            "No relevant content found in the FY26 financial documents "
            f"for this query{f' (quarter={normalised})' if normalised else ''}."
        )

    blocks: list[str] = []
    for doc in documents:
        source = doc.metadata.get("source", "unknown")
        section = doc.metadata.get("header_1") or doc.metadata.get("header_2") or "—"
        blocks.append(f"[Source: {source} | Section: {section}]\n{doc.page_content}")

    return "\n\n---\n\n".join(blocks)
