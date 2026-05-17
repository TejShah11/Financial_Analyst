# tests/

Test suite for LedgerMind. Currently contains the Sprint 5 RAG evaluation framework; unit tests for individual components can be added here in future sprints.

## Directory layout

```
tests/
├── __init__.py
└── evaluation/     Groq-based LLM-as-judge evaluation pipeline (see evaluation/README.md)
```

## Running tests

```bash
# Run the full evaluation pipeline (requires backend server running)
uv run python -m tests.evaluation.run_eval
```

See [evaluation/README.md](evaluation/README.md) for full details and options.
