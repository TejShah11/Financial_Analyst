# frontend/web/ — Next.js Chatbot UI

Production-grade React/TypeScript chatbot for LedgerMind. Dark-professional design with blue/violet gradient accents, NDJSON streaming, multi-session management, and rich Markdown rendering.

## Stack

| Technology | Version | Role |
|---|---|---|
| Next.js | 14 (App Router) | Framework |
| React | 18 | UI runtime |
| TypeScript | 5 | Type safety |
| Tailwind CSS | 3 + `@tailwindcss/typography` | Styling |
| `react-markdown` + `remark-gfm` | 9 | Markdown and GFM table rendering |
| `lucide-react` | — | Icons |
| `framer-motion` | 11 | Animation-ready |
| `uuid` | 11 | Session ID generation |

## Prerequisites

- Node.js 18+ (LTS recommended)
- FastAPI backend running at `http://localhost:8000`

## Setup & run

```bash
cd frontend/web
npm install
npm run dev         # development server on http://localhost:3000
```

To build for production:
```bash
npm run build
npm start
```

## Environment

Copy `.env.local` (already present, not committed) or create one:
```
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
```

## Component architecture

```
src/
├── app/
│   ├── layout.tsx          Root layout: metadata, Google Fonts import, global CSS
│   ├── page.tsx            Root page — renders <ChatInterface />
│   └── globals.css         CSS custom properties, scrollbar, animation keyframes, prose overrides
│
├── components/
│   ├── ChatInterface.tsx   Main stateful component: session management, streaming, layout
│   ├── ChatMessage.tsx     Individual message: Markdown rendering, source badges, download button
│   ├── ProgressIndicator.tsx  Live streaming step list with pulse/check animations
│   └── Sidebar.tsx         Session history (localStorage), New Chat button, knowledge base list
│
├── lib/
│   ├── api.ts              NDJSON stream reader (fetch + ReadableStream), history fetch
│   └── sessions.ts         localStorage session persistence helpers
│
└── types/
    └── index.ts            TypeScript interfaces: Message, Session, StreamEvent variants
```

## Streaming protocol

The UI calls `POST /chat/stream` and reads the NDJSON response line by line:

```
{"type": "progress", "node": "retrieval", "label": "Searching the financial documents..."}
{"type": "progress", "node": "drafter",   "label": "Drafting the analysis..."}
{"type": "result",   "answer": "...", "sources": [...], "verified": true, "file_url": "/download/..."}
```

Each `progress` event adds a step to the `ProgressIndicator`. The `result` event replaces the streaming placeholder with the final message.

## Session management

- `session_id` (UUID v4) is stored in the URL as `?session=<id>` and in `localStorage`
- On page load, if `?session=` is present, conversation history is restored from `GET /history/{id}`
- New Chat creates a fresh UUID, updates the URL, and resets state
- Up to 20 recent sessions are listed in the sidebar with title + relative timestamp

## Design tokens

| Token | Value | Used for |
|---|---|---|
| `--bg-base` | `#050a14` | Page background |
| `--bg-surface` | `#0d1626` | Sidebar, header, input bar |
| `--bg-raised` | `#111f35` | Message bubbles, cards |
| Gradient | `#3b82f6 → #8b5cf6` | Brand text, send button, avatar |
| User bubble | `#1e3f6e → #25336e` | User message background |
| `--text-primary` | `#e2e8f0` | Body text |
| `--text-secondary` | `#94a3b8` | Subtitles, session list |
| `--text-muted` | `#475569` | Labels, KB items |
