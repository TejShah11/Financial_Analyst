# backend/ingestion/

PDF-to-vector-store ingestion pipeline. Run once to populate ChromaDB before starting the server.

## Files

| File | Purpose |
|---|---|
| `parser.py` | Wraps LlamaParse to extract PDF → Markdown with caching |
| `pipeline.py` | Orchestrates: scan `data/raw/` → parse → chunk → embed → store in ChromaDB |

## How to run

```bash
# From financial-analyst-agent/
uv run python -m backend.ingestion.pipeline
```

Processes all `.pdf` files in `data/raw/`. Already-parsed files are cached in `data/processed/` as `.md` so re-runs skip the expensive LlamaParse API call. Run again only when new documents are added to `data/raw/`.

## Pipeline stages

### 1. Parsing (`parser.py`)
- Uses **LlamaParse** (LlamaCloud API) to convert PDFs to clean Markdown
- Handles multi-column press-release layouts, embedded tables, and footnotes better than standard PDF libraries
- Caches output as `data/processed/<filename>.md`; subsequent runs load from cache
- Boilerplate filter removes repeated page headers/footers (`"infosys integrated annual report"`, etc.) that would otherwise become hundreds of near-duplicate junk chunks

### 2. Header-based parent splitting
- `MarkdownHeaderTextSplitter` splits on `#` and `##` headers
- Produces *parent sections* that keep financial tables attached to their section title
- Metadata tagged: `source` (filename), `doc_type` (`press_release` / `annual_report`), `quarter` (e.g., `q1`, `q2`, derived from filename pattern)

### 3. Child chunking
- `RecursiveCharacterTextSplitter` divides oversized parent sections into child chunks
- `CHUNK_SIZE = 1_000` characters, `CHUNK_OVERLAP = 150`
- Children inherit parent metadata so provenance is preserved all the way to retrieval

### 4. Embedding and storage
- `BAAI/bge-large-en-v1.5` (local, via SentenceTransformers) produces 1,024-dim vectors
- Chunks are upserted into ChromaDB at `data/chroma_db/`

## Data sources expected in `data/raw/`

| File | Type | Quarter |
|---|---|---|
| `ifrs-usd-press-release_q1.pdf` | Press release | Q1 FY26 |
| `ifrs-usd-press-release_q2.pdf` | Press release | Q2 FY26 |
| `ifrs-usd-press-release_q3.pdf` | Press release | Q3 FY26 |
| `ifrs-usd-press-release_q4.pdf` | Press release | Q4 FY26 |
| `infosys-ar-25.pdf` | Annual report | FY25 |
| `500209.csv` | Stock price history | BSE daily OHLCV |
| `500209.xls` | Investor data workbook | Multi-sheet summary |

CSV and XLS files are **not** ingested into ChromaDB — they are loaded as Pandas DataFrames directly by the quantitative tool at runtime.
