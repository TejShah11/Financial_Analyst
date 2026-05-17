# backend/

The entire server-side of LedgerMind — LangGraph agent, FastAPI HTTP layer, ChromaDB retrieval, ingestion pipeline, and report generation utilities.

## Directory layout

```
backend/
├── agents/          LangGraph DAG: nodes, graph wiring, state schema, prompts, tools
├── api/             FastAPI application: routes, schemas, CORS, dependencies
├── core/            Pydantic Settings (reads .env), path constants
├── database/        ChromaDB client + retriever abstraction
├── ingestion/       PDF → Markdown → chunks → ChromaDB pipeline
└── utils/           PDF and Excel report generators, custom fonts
```

## Key dependencies

| Package | Role |
|---|---|
| `langgraph` | Stateful agent graph with conditional routing |
| `langchain-google-genai` | Gemini LLM + (originally) embeddings |
| `langchain-huggingface` | Local BGE embedding model |
| `langchain-chroma` | ChromaDB vectorstore wrapper |
| `sentence-transformers` | `bge-large-en-v1.5` embedding + `bge-reranker-base` cross-encoder |
| `fastapi` + `uvicorn` | HTTP API and NDJSON streaming |
| `pydantic-settings` | Typed environment config |
| `fpdf2` | PDF report generation |
| `openpyxl` + `pandas` | Excel export and quantitative analysis |
| `llama-parse` | High-fidelity PDF-to-Markdown extraction |

## Running the backend

```bash
# From financial-analyst-agent/
uv run uvicorn backend.api.main:app --reload --port 8000
```

The server starts at `http://localhost:8000`. Check `GET /health` to confirm it's live.

## Environment variables required

See `.env` (never committed):

```
GEMINI_API_KEY=...
LLAMA_CLOUD_API_KEY=...
```

## Before first use — ingest documents

```bash
uv run python -m backend.ingestion.pipeline
```

This parses all PDFs in `data/raw/` and loads chunks into ChromaDB at `data/chroma_db/`. Run once; the vector store persists across restarts.
