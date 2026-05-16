"""Application configuration loaded from environment variables.

A single :class:`Settings` instance is the source of truth for API keys and
on-disk data locations. Use :func:`get_settings` everywhere so the ``.env``
file is parsed only once per process.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly typed application settings.

    API keys are required and intentionally have no defaults so a missing
    credential fails fast at startup rather than mid-pipeline. Data directories
    default to project-relative paths and are created on demand by the callers
    that own them (the ingestion pipeline and the Chroma client).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --- Credentials ---------------------------------------------------------
    GEMINI_API_KEY: str = Field(
        ..., description="Google Gemini API key used for embeddings and the LLM."
    )
    LLAMA_CLOUD_API_KEY: str = Field(
        ..., description="LlamaCloud API key used by LlamaParse for PDF extraction."
    )

    # --- Data locations ------------------------------------------------------
    RAW_DATA_DIR: Path = Field(
        default=Path("./data/raw"),
        description="Source PDFs / CSVs / Excel files awaiting ingestion.",
    )
    PROCESSED_DATA_DIR: Path = Field(
        default=Path("./data/processed"),
        description="Intermediate Markdown produced by LlamaParse.",
    )
    CHROMA_DB_DIR: Path = Field(
        default=Path("./data/chroma_db"),
        description="Persistent ChromaDB store (SQLite + Parquet segments).",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide :class:`Settings` singleton."""
    return Settings()
