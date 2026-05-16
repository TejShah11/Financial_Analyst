"""ChromaDB-backed implementation of :class:`BaseFinancialRetriever`.

A local ``chromadb.PersistentClient`` is wrapped in LangChain's ``Chroma``
vector store. Embeddings are generated **locally** with the SentenceTransformers
model ``BAAI/bge-large-en-v1.5`` — a top-tier open retrieval model — so indexing
has no API quota, rate limit, or per-call cost.
"""

from __future__ import annotations

import logging
from typing import Any

import chromadb
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings

from backend.core.config import get_settings
from backend.database.interfaces import BaseFinancialRetriever

logger = logging.getLogger(__name__)

DEFAULT_COLLECTION = "financial_documents"

# Local SentenceTransformers embedding model. bge-large-en-v1.5 is a strong,
# widely benchmarked retrieval model (1024-dim). Embeddings are normalised so
# Chroma's cosine/L2 search behaves consistently. Running locally removes the
# Gemini free-tier embedding quota entirely.
EMBEDDING_MODEL = "BAAI/bge-large-en-v1.5"
EMBEDDING_DEVICE = "cpu"

# Documents are indexed in batches purely for progress visibility on the large
# annual report; local embedding has no rate limit so no retry/backoff needed.
ADD_BATCH_SIZE = 256


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
        self._embeddings = HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL,
            model_kwargs={"device": EMBEDDING_DEVICE},
            encode_kwargs={"normalize_embeddings": True},
        )
        self._store = Chroma(
            client=self._client,
            collection_name=collection_name,
            embedding_function=self._embeddings,
        )
        logger.info(
            "ChromaFinancialRetriever ready (collection=%s, model=%s, path=%s)",
            collection_name,
            EMBEDDING_MODEL,
            settings.CHROMA_DB_DIR,
        )

    def add_documents(self, documents: list[Document]) -> list[str]:
        """Embed and persist ``documents`` into the Chroma collection.

        Documents are indexed in fixed-size batches so progress is visible while
        the large annual report is processed.
        """
        if not documents:
            logger.warning("add_documents called with an empty list; skipping.")
            return []

        all_ids: list[str] = []
        total = len(documents)
        for start in range(0, total, ADD_BATCH_SIZE):
            batch = documents[start : start + ADD_BATCH_SIZE]
            all_ids.extend(self._store.add_documents(batch))
            logger.info(
                "Indexed %d/%d chunks into '%s'.",
                len(all_ids),
                total,
                self._collection_name,
            )
        return all_ids

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
