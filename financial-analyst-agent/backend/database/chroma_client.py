"""ChromaDB-backed implementation of :class:`BaseFinancialRetriever`.

A local ``chromadb.PersistentClient`` is wrapped in LangChain's ``Chroma``
vector store. Embeddings are generated **locally** with the SentenceTransformers
model ``BAAI/bge-large-en-v1.5`` — a top-tier open retrieval model — so indexing
has no API quota, rate limit, or per-call cost.

Retrieval is two-stage: a wide bi-encoder vector search pulls a candidate pool,
then a local cross-encoder re-ranker (``BAAI/bge-reranker-base``) re-scores each
candidate against the query and only the most relevant few are returned. This
fixes the precision gap of pure vector similarity without flooding the LLM with
low-relevance chunks.
"""

from __future__ import annotations

import logging
from typing import Any

import chromadb
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from sentence_transformers import CrossEncoder

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

# Cross-encoder re-ranker (same family as the embedding model). The bi-encoder
# first fetches RERANK_CANDIDATE_POOL candidates; the re-ranker then scores each
# (query, chunk) pair jointly and the caller keeps only the top few.
RERANKER_MODEL = "BAAI/bge-reranker-base"
RERANK_CANDIDATE_POOL = 35

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
        # The re-ranker is heavy (~1.1 GB) and only needed for queries, so it is
        # loaded lazily on the first get_context call — never during ingestion.
        self._reranker: CrossEncoder | None = None
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

    def _get_reranker(self) -> CrossEncoder:
        """Lazily load the cross-encoder re-ranker (once, on first query)."""
        if self._reranker is None:
            logger.info("Loading cross-encoder re-ranker: %s", RERANKER_MODEL)
            self._reranker = CrossEncoder(RERANKER_MODEL, device=EMBEDDING_DEVICE)
        return self._reranker

    def get_context(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
        k: int = 5,
    ) -> list[Document]:
        """Return the ``k`` most relevant documents for ``query``.

        Two-stage retrieval: a wide bi-encoder vector search builds a candidate
        pool, then the cross-encoder re-ranker re-scores every candidate and the
        top ``k`` are returned.

        ``filters`` is forwarded to Chroma's metadata ``where`` clause, enabling
        precise period-scoped retrieval (e.g. ``{"quarter": "Q2"}``).
        """
        # Stage 1 — wide bi-encoder retrieval.
        pool_size = max(RERANK_CANDIDATE_POOL, k)
        candidates = self._store.similarity_search(
            query=query, k=pool_size, filter=filters
        )
        if len(candidates) <= k:
            return candidates

        # Stage 2 — cross-encoder re-ranking of the candidate pool.
        reranker = self._get_reranker()
        scores = reranker.predict([(query, doc.page_content) for doc in candidates])
        ranked = sorted(
            zip(scores, candidates), key=lambda pair: float(pair[0]), reverse=True
        )
        top_documents = [doc for _, doc in ranked[:k]]
        logger.info(
            "Retrieved %d candidates, re-ranked to top %d.",
            len(candidates),
            len(top_documents),
        )
        return top_documents
