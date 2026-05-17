# backend/api/

FastAPI application — HTTP interface between the frontends and the LangGraph agent.

## Files

| File | Purpose |
|---|---|
| `main.py` | FastAPI app factory: attaches CORS middleware, mounts the router |
| `endpoints.py` | All route handlers: `/chat`, `/chat/stream`, `/history/{id}`, `/download/{file}` |
| `schemas.py` | Pydantic request/response models (`ChatRequest`, `ChatResponse`) |
| `dependencies.py` | `get_agent()` FastAPI dependency that injects the compiled LangGraph app |

## Endpoints

### `POST /chat`
Synchronous. Runs the full agent graph and returns the complete answer with a download link.

**Request body:**
```json
{ "query": "What was Q1 FY26 revenue?", "session_id": "abc123" }
```

**Response:**
```json
{
  "answer": "Infosys reported revenue of $4,941 million...",
  "intent": "narrative",
  "sources": ["ifrs-usd-press-release_q1.pdf"],
  "verified": true,
  "file_url": "/download/report_abc12345.pdf"
}
```

### `POST /chat/stream`
Streaming (NDJSON). Emits one JSON line per LangGraph node as it runs, then the final result. Used by both the Streamlit and Next.js UIs.

**Stream events:**
```jsonl
{"type": "progress", "node": "query_planner", "label": "Understanding the question..."}
{"type": "progress", "node": "retrieval",     "label": "Searching the financial documents..."}
{"type": "result",   "answer": "...", "sources": [...], "verified": true, "file_url": "..."}
```
On error: `{"type": "error", "detail": "..."}`.

### `GET /history/{session_id}`
Returns the conversation history for a session so the UI can restore it after a page refresh.

**Response:**
```json
{ "messages": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}] }
```

### `GET /download/{filename}`
Serves a previously generated PDF or Excel artifact from `data/exports/`. Path traversal is prevented by stripping directory components with `Path(filename).name`.

### `GET /health`
Liveness probe. Returns `{"status": "healthy"}`.

## CORS

All origins are allowed (`allow_origins=["*"]`) with `allow_credentials=False`. This is intentional for local development — the browser-based Next.js UI at `localhost:3000` calls the API at `localhost:8000` directly.

## Node progress labels

The streaming endpoint maps each LangGraph node name to a human-readable label via `NODE_LABELS` in `endpoints.py`. This is what appears in the streaming progress steps in the UI.
