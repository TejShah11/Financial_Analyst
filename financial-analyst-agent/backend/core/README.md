# backend/core/

Application-wide configuration and shared constants.

## Files

| File | Purpose |
|---|---|
| `config.py` | `Settings` (Pydantic BaseSettings) — reads `.env`, exposes typed paths and API keys |

## Settings reference

| Variable | Type | Default | Description |
|---|---|---|---|
| `GEMINI_API_KEY` | `str` | **required** | Google Gemini API key |
| `LLAMA_CLOUD_API_KEY` | `str` | **required** | LlamaCloud / LlamaParse API key |
| `RAW_DATA_DIR` | `Path` | `./data/raw` | Source PDFs, CSVs, XLS files |
| `PROCESSED_DATA_DIR` | `Path` | `./data/processed` | Cached LlamaParse Markdown outputs |
| `CHROMA_DB_DIR` | `Path` | `./data/chroma_db` | Persistent ChromaDB vector store |
| `EXPORTS_DIR` | `Path` | `./data/exports` | Generated PDF/Excel download artifacts |
| `CHECKPOINT_DB` | `Path` | `./data/agent_memory.sqlite` | LangGraph SqliteSaver memory |

All variables are loaded from the `.env` file in the project root. The `Settings` instance is cached via `@lru_cache` so `.env` is parsed only once per process.

## Usage

```python
from backend.core.config import get_settings

settings = get_settings()
print(settings.EXPORTS_DIR)  # Path('./data/exports')
```
