"""LedgerMind — Streamlit frontend for the financial analyst agent.

Run with:  uv run streamlit run frontend/app.py

Connects to the FastAPI backend (``http://localhost:8000``), keeps a
multi-turn conversation (one ``session_id`` per browser session), streams
live backend progress, and surfaces downloadable PDF/Excel artifacts.
"""

from __future__ import annotations

import json
import uuid

import requests
import streamlit as st

from components.chat_interface import render_chat_history
from components.sidebar import render_sidebar

# --- Backend wiring --------------------------------------------------------- #
BACKEND_URL = "http://localhost:8000"
STREAM_ENDPOINT = f"{BACKEND_URL}/chat/stream"
# The agent loads a local embedding model and makes several LLM calls, so the
# gap between streamed progress events can be long — keep a generous timeout.
REQUEST_TIMEOUT_SECONDS = 180

_WELCOME_MESSAGE = (
    "Hello! I'm **LedgerMind**, your Infosys FY26 financial analyst.\n\n"
    "Ask me about quarterly results, the annual report, or share-price data — "
    "and feel free to ask **follow-up questions**; I remember the conversation. "
    "Every answer comes with a downloadable PDF or Excel file."
)


def _init_session_state() -> None:
    """Seed the welcome message and a conversation id on first load."""
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {"role": "assistant", "content": _WELCOME_MESSAGE}
        ]
    if "session_id" not in st.session_state:
        # One thread id per browser session — gives the agent multi-turn memory.
        st.session_state.session_id = uuid.uuid4().hex


def _error_message(detail: str) -> dict:
    """Build an assistant message describing a backend failure."""
    return {
        "role": "assistant",
        "content": f":warning: {detail}",
        "intent": "error",
        "sources": [],
    }


def _stream_backend(prompt: str, status) -> dict:
    """Call the streaming endpoint, updating ``status`` with live progress.

    Returns the assistant message dict (or a friendly error message).
    """
    payload = {"query": prompt, "session_id": st.session_state.session_id}
    try:
        with requests.post(
            STREAM_ENDPOINT,
            json=payload,
            stream=True,
            timeout=REQUEST_TIMEOUT_SECONDS,
        ) as response:
            response.raise_for_status()

            result: dict | None = None
            for raw_line in response.iter_lines():
                if not raw_line:
                    continue
                event = json.loads(raw_line)
                event_type = event.get("type")

                if event_type == "progress":
                    label = event.get("label", "Working...")
                    status.update(label=label)
                    status.write(f"• {label}")
                elif event_type == "result":
                    result = event
                elif event_type == "error":
                    return _error_message(event.get("detail", "Unknown backend error."))

            if result is None:
                return _error_message("The backend stream ended without a result.")

            message: dict = {
                "role": "assistant",
                "content": result.get("answer", "_(no answer returned)_"),
                "intent": result.get("intent", ""),
                "sources": result.get("sources", []),
            }
            file_url = result.get("file_url")
            if file_url:
                message["file_url"] = f"{BACKEND_URL}{file_url}"
            return message

    except requests.exceptions.ConnectionError:
        return _error_message(
            "**Cannot reach the analysis backend.** Start the FastAPI server "
            "(`./scripts/run_server.sh`) so it is live at `http://localhost:8000`."
        )
    except requests.exceptions.Timeout:
        return _error_message(
            "**The request timed out.** The analysis took longer than expected — "
            "please try again."
        )
    except requests.exceptions.RequestException as exc:
        return _error_message(f"**Unexpected error contacting the backend.** {exc}")


def main() -> None:
    """Render the LedgerMind chat application."""
    st.set_page_config(
        page_title="Financial Analyst Agent",
        page_icon=":bar_chart:",
        layout="wide",
    )

    _init_session_state()
    render_sidebar()

    st.title(":bar_chart: Infosys Financial Analyst Agent")
    st.caption(
        "Multi-route agentic RAG over Infosys FY26 filings — narrative "
        "retrieval, quantitative analysis, follow-up memory, and report generation."
    )

    render_chat_history()

    if prompt := st.chat_input("Ask about Infosys financials..."):
        # 1. Record and show the user's message.
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # 2. Stream the backend run, showing each step live.
        with st.chat_message("assistant"):
            with st.status("Analyzing financial data...", expanded=True) as status:
                assistant_message = _stream_backend(prompt, status)
                state = "error" if assistant_message.get("intent") == "error" else "complete"
                status.update(label="Done", state=state, expanded=False)

            st.markdown(assistant_message["content"])
            sources = assistant_message.get("sources", [])
            if sources:
                st.caption("📄 **Sources:** " + " · ".join(sources))
            file_url = assistant_message.get("file_url")
            if file_url:
                filename = file_url.rstrip("/").rsplit("/", 1)[-1] or "file"
                st.link_button(f"Download  {filename}", file_url)

        # 3. Persist the assistant message and refresh the UI.
        st.session_state.messages.append(assistant_message)
        st.rerun()


if __name__ == "__main__":
    main()
