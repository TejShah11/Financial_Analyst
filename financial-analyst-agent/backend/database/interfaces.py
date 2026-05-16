"""Repository abstraction for the financial document vector store.

The agent layer depends only on :class:`BaseFinancialRetriever`, never on a
concrete database. This keeps ChromaDB swappable for a distributed store later
without touching retrieval-tool or agent code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from langchain_core.documents import Document


class BaseFinancialRetriever(ABC):
    """Abstract contract for indexing and querying financial documents."""

    @abstractmethod
    def add_documents(self, documents: list[Document]) -> list[str]:
        """Embed and persist ``documents`` in the vector store.

        Args:
            documents: Chunked LangChain documents with attached metadata.

        Returns:
            The store-assigned IDs of the persisted documents.
        """
        raise NotImplementedError

    @abstractmethod
    def get_context(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
        k: int = 5,
    ) -> list[Document]:
        """Retrieve the most relevant documents for ``query``.

        Args:
            query: Natural-language search string (already coreference-resolved).
            filters: Optional metadata filter, e.g. ``{"quarter": "Q2"}``, used
                for quarter-over-quarter comparisons.
            k: Maximum number of documents to return.

        Returns:
            Documents ordered by descending relevance.
        """
        raise NotImplementedError
