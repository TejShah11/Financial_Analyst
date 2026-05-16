#!/bin/bash
echo "Starting LedgerMind Core API..."
uv run uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 --reload
