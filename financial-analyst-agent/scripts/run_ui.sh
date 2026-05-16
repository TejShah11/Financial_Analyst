#!/bin/bash
echo "Starting LedgerMind Streamlit Interface..."
uv run streamlit run frontend/app.py --server.port 8501
