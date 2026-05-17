# frontend/

Two parallel user interfaces for LedgerMind — a Streamlit prototype (Sprint 4) and a production-grade Next.js chatbot (Sprint 6). Both connect to the same FastAPI backend.

## Directory layout

```
frontend/
├── app.py                     Streamlit application entry point
├── components/
│   ├── chat_interface.py      Renders conversation history (Streamlit)
│   └── sidebar.py             Sidebar: knowledge base list, reset button (Streamlit)
└── web/                       Next.js 14 chatbot (see web/README.md)
```

## Streamlit UI

A quick-to-run prototype using `streamlit`. Connects to the backend streaming endpoint and renders answers with Streamlit's native markdown support.

**Run:**
```bash
# From financial-analyst-agent/
uv run streamlit run frontend/app.py
```
Opens at `http://localhost:8501`.

**Features:**
- Live streaming progress (Streamlit `st.status`)
- Source citations below each answer
- PDF/Excel download link buttons
- Session persistence via URL `?session=` query param
- Conversation history restored from `GET /history/{id}` on refresh
- "Clear Conversation" button in sidebar

## Next.js UI

A production-quality chatbot built with React, TypeScript, and Tailwind CSS. See [web/README.md](web/README.md) for full details.

**Run:**
```bash
cd frontend/web
npm run dev        # http://localhost:3000
```

## Backend dependency

Both UIs require the FastAPI server to be running:
```bash
uv run uvicorn backend.api.main:app --reload --port 8000
```
