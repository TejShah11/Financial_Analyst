"""ChromaDB-backed implementation of :class:`BaseFinancialRetriever`.

A local ``chromadb.PersistentClient`` is wrapped in LangChain's ``Chroma``
vector store. Embeddings are generated with Google's ``text-embedding-004``
model, matching the Gemini foundation model used elsewhere in the system.
"""

from __future__ import annotations

import logging
from typing import Any

import chromadb
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from backend.core.config import get_settings
from backend.database.interfaces import BaseFinancialRetriever

logger = logging.getLogger(__name__)

DEFAULT_COLLECTION = "financial_documents"
EMBEDDING_MODEL = "models/text-embedding-004"


class ChromaFinancialRetriever(BaseFinancialRetriever):
    """Persistent ChromaDB retriever for Infosys financial documents."""

    def __init__(self, collection_name: str = DEFAULT_COLLECTION) -> None:
        """Initialise the persistent client, embeddings, and vector store.

        Args:
            collection_name: Name of the Chroma collection to read/write.
        """
        settings = get_settings()
        settings.CHROMA_DB_DIR.mkdir(parents=True, exist_ok=True)

        self._collection_name = collection_name
        self._client = chromadb.PersistentClient(path=str(settings.CHROMA_DB_DIR))
        self._embeddings = GoogleGenerativeAIEmbeddings(
            model=EMBEDDING_MODEL,
            google_api_key=settings.GEMINI_API_KEY,
        )
        self._store = Chroma(
            client=self._client,
            collection_name=collection_name,
            embedding_function=self._embeddings,
        )
        logger.info(
            "ChromaFinancialRetriever ready (collection=%s, path=%s)",
            collection_name,
            settings.CHROMA_DB_DIR,
        )

    def add_documents(self, documents: list[Document]) -> list[str]:
        """Embed and persist ``documents`` into the Chroma collection."""
        if not documents:
            logger.warning("add_documents called with an empty list; skipping.")
            return []
        ids = self._store.add_documents(documents)
        logger.info("Indexed %d chunks into '%s'.", len(ids), self._collection_name)
        return ids

    def get_context(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
        k: int = 5,
    ) -> list[Document]:
        """Return the top-``k`` documents most similar to ``query``.

        ``filters`` is forwarded to Chroma's metadata ``where`` clause, enabling
        precise period-scoped retrieval (e.g. ``{"quarter": "Q2"}``).
        """
        return self._store.similarity_search(query=query, k=k, filter=filters)
