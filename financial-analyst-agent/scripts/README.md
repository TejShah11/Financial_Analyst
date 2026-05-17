# scripts/

Convenience shell scripts and a manual test harness.

## Files

| File | Purpose |
|---|---|
| `run_server.sh` | Start the FastAPI backend with uvicorn in reload mode |
| `run_ui.sh` | Start the Streamlit frontend |
| `test_agent.py` | CLI script for sending a single question to the agent without the UI |

## run_server.sh

```bash
#!/usr/bin/env bash
# From financial-analyst-agent/
uv run uvicorn backend.api.main:app --reload --port 8000
```

Run from the `financial-analyst-agent/` directory:
```bash
bash scripts/run_server.sh
```

## run_ui.sh

```bash
#!/usr/bin/env bash
uv run streamlit run frontend/app.py
```

Opens the Streamlit UI at `http://localhost:8501`.

## test_agent.py

A quick command-line smoke test. Sends one question directly through the LangGraph agent (bypassing HTTP) and prints the answer.

```bash
# Default question
uv run python scripts/test_agent.py

# Custom question
uv run python scripts/test_agent.py "What was the free cash flow in Q2 FY26?"
```

Useful for:
- Verifying the agent works after environment changes
- Debugging node outputs without starting the full HTTP server
- Quick iteration on prompt changes
