# backend/database/

ChromaDB client and retriever abstraction layer.

## Files

| File | Purpose |
|---|---|
| `interfaces.py` | Abstract base class `FinancialRetriever` (protocol/interface) |
| `chroma_client.py` | `ChromaFinancialRetriever` — concrete implementation wrapping `langchain-chroma` |

## How it works

`ChromaFinancialRetriever` is instantiated once (singleton via `lru_cache`) and shared across all requests. It:

1. Opens the persistent ChromaDB store at `data/chroma_db/` using `PersistentClient`
2. Loads the `BAAI/bge-large-en-v1.5` embedding model (1,024 dimensions, local, no API call)
3. Exposes a `search(query, k, quarter_filter)` method used by the `retrieval_node`

### Retrieval flow inside `vector_tool.py`

```
query string
    │
    ▼
BGE-large embed → dense vector
    │
    ▼
ChromaDB ANN search (top-20 candidates)
    │
    ▼
Optional metadata pre-filter (quarter == "q1" etc.)
    │
    ▼
bge-reranker-base cross-encoder rescoring
    │
    ▼
Top-5 chunks returned as context string + source list
```

The cross-encoder reranker (`BAAI/bge-reranker-base`) re-scores the top-20 candidates using the full (query, chunk) pair rather than independent embeddings. This significantly improves precision for financial queries where small phrasing differences matter (e.g., "operating margin" vs "EBIT margin").

## Metadata schema per chunk

```python
{
    "source":   "ifrs-usd-press-release_q1.pdf",
    "doc_type": "press_release",          # or "annual_report"
    "quarter":  "q1",                     # q1 / q2 / q3 / q4 / "" (annual report)
    "header_1": "Financial Highlights",  # from MarkdownHeaderTextSplitter
    "header_2": "Revenue"                # nested header (if present)
}
```

## Persistence

ChromaDB stores data in `data/chroma_db/` as SQLite + binary segment files. The directory is created automatically on first run. Once ingested, the store persists across server restarts — there is no need to re-ingest unless new documents are added.
