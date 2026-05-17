# Reflection — LedgerMind Financial Analyst Chatbot

---

## 1. What makes your chatbot feel intelligent rather than just doing keyword search? What did you specifically do to get there?

Several design decisions together push the system past keyword lookup:

**Query planning before any retrieval.** Every question passes through a dedicated `query_planner` node that does two things before a single vector search runs: it classifies the intent (`narrative`, `quantitative`, `hybrid`, or `chat`) and rewrites the question into a fully self-contained form. This means a follow-up like *"How did that compare to the previous quarter?"* is expanded to *"How did Infosys's operating margin in Q2 FY26 compare to Q1 FY26?"* before retrieval even begins. A pure keyword system would search the vague pronoun and find nothing useful.

**Two distinct retrieval tracks wired conditionally.** The graph routes narrative questions through ChromaDB (semantic vector search over 1,000-char parent-child chunks, with a `bge-reranker-base` cross-encoder pass at the end to re-score the top-20 candidates). Quantitative questions — anything involving exact numbers, time-series, price histories — are routed to a Pandas REPL that executes real Python against pre-loaded DataFrames of the stock CSV and investor Excel workbook. Hybrid questions run both tracks in sequence, so a question like *"Did the share price move in line with revenue growth?"* draws on document text and computed figures simultaneously.

**A Drafter → Critic self-correction loop.** The first draft is never returned to the user directly. A separate `critic_node` checks the draft against the retrieved evidence and flags specific factual discrepancies with corrective instructions. If errors are found, the draft goes back to the drafter (up to `MAX_REVISIONS = 2` times). This means a draft that confuses Q1 margins with Q2 margins gets caught internally and corrected before the user sees it, rather than hallucinating silently.

**SqliteSaver multi-turn memory.** Conversation state is persisted to `data/agent_memory.sqlite` keyed by `session_id`. Each new turn's `query_planner` has access to the full prior message list, so references like *"What about the net new percentage?"* resolve correctly without the user repeating context. This survives server restarts — a fresh uvicorn process can continue any previous conversation thread.

**Semantic chunking with provenance metadata.** The ingestion pipeline uses a two-stage split: `MarkdownHeaderTextSplitter` first carves documents at `#`/`##` header boundaries (so a financial table stays attached to the section header that names it), then `RecursiveCharacterTextSplitter` divides oversized sections into 1,000-character child chunks with 150-character overlap. Each chunk is tagged with `source`, `doc_type`, and `quarter` metadata. At query time, the retriever can pre-filter on quarter (e.g., only search Q3 press release chunks when the planner classifies the question as Q3-specific), drastically reducing noise from unrelated quarters.

---

## 2. Where does it still fall short? What would a real analyst notice that your system gets wrong or misses?

The honest gaps are in three areas:

**Deep cross-document synthesis.** Questions spanning all five source documents simultaneously (e.g., *"How does the FY25 annual report revenue compare to each quarter of FY26?"*) rely on the LLM to synthesise a flat context block drawn from multiple files. When the context window fills up, chunks from one document can crowd out another. A dedicated summarisation pass over each document before the drafter runs would close this gap.

**Schema sensitivity in the quantitative track.** The Pandas REPL requires exact column name spelling. If the LLM guesses a plausible-but-wrong column name, the REPL returns a `KeyError`. A schema dictionary injected into the system prompt (which already partially exists as `_QUANT_INSTRUCTION`) mostly handles this, but edge cases remain.

**No charting capability.** A real analyst would immediately ask to visualise trends across quarters. The system produces clean Markdown tables and downloadable Excel files, but generates no charts or plots. The underlying data is all present — adding a `matplotlib` or `plotly` rendering step in the format node would complete the picture.

---

## 3. Which AI tools did you use to build this, and what did you have to fix or override yourself?

**LlamaParse (LlamaCloud)** — Used for PDF-to-Markdown extraction. LlamaParse handles complex multi-column financial press releases and tables far better than `pdfplumber` or `PyMuPDF`. However, it repeats running headers and footers (e.g., *"Infosys Integrated Annual Report"*) on every page, which became hundreds of near-duplicate junk chunks polluting vector retrieval. I had to write a post-processing step (`_BOILERPLATE_PHRASES` filter in `pipeline.py`) that strips these before chunking.

**Google Gemini (via `langchain-google-genai`)** — The primary LLM for all agent nodes. I started with `gemini-1.5-pro` (retired mid-project), moved to `gemini-2.0-flash` (daily quota exhausted on the free tier within hours of testing), and finally settled on `gemini-3.1-flash-lite` which sits in a separate quota bucket. The model switch required tuning all prompts because the flash-lite model is less instruction-following than pro — it would sometimes ignore the output format spec and return prose instead of structured JSON.

**BAAI/bge-large-en-v1.5 + bge-reranker-base (SentenceTransformers)** — Used for embeddings and reranking respectively, both running locally. I originally used `text-embedding-004` (Google, retired 404) then `gemini-embedding-001` (Google, hit 100 RPM rate limit immediately). Switching to the local BGE model eliminated the API rate-limit problem entirely, at the cost of a ~2 GB model download and longer first-query cold start.

**LangGraph** — The graph DSL is expressive but the `hybrid` routing case (retrieval → quantitative → drafter) required careful conditional edge wiring; the documentation examples all show linear graphs. I had to debug why `quantitative` was being called twice on hybrid questions (it was reaching `drafter` via both `retrieval → drafter` and `quantitative → drafter` edges), and resolved it by adding a dedicated `_route_after_retrieval` function that only branches to `quantitative` when `intent == "hybrid"`.

**ChromaDB + LangChain** — The parent-child chunking pattern is not built into LangChain's standard `ChromaVectorStore`. I implemented it manually: the parent (header section) is stored as a separate document with its own embedding, and children inherit its metadata. This ensures that when a table header is matched by semantic search, the full section including the table body is returned to the drafter.

**Groq (llama-3.3-70b-versatile) as evaluation judge** — Used in Sprint 5 to evaluate chatbot answers against the golden dataset. The judge initially gave inconsistent verdicts: it would score `0.70` but then emit `"verdict": "FAIL"` in the same JSON object. I resolved this by computing `PASS/FAIL` deterministically in Python from the numeric score, never trusting the LLM's own verdict field. I also had to iterate the judge prompt three times before it stopped failing correct answers for being in a different number format (e.g., rejecting `$5.1 billion` when the ground truth said `5,076 million`).

**Windows MAX_PATH issue** — `llama-cloud==0.1.46` ships an auto-generated filename exceeding Windows' 260-character path limit, causing `FileNotFoundError` on install. Fixed by enabling `HKLM\SYSTEM\CurrentControlSet\Control\FileSystem\LongPathsEnabled = 1` in the Windows registry.
