"""LedgerMind — Streamlit frontend for the financial analyst agent.

Run with:  uv run streamlit run frontend/app.py

Connects to the FastAPI backend (``http://localhost:8000``), maintains chat
history in session state, and surfaces downloadable PDF/Excel artifacts.
"""

from __future__ import annotations

import requests
import streamlit as st

from components.chat_interface import render_chat_history
from components.sidebar import render_sidebar

# --- Backend wiring --------------------------------------------------------- #
BACKEND_URL = "http://localhost:8000"
CHAT_ENDPOINT = f"{BACKEND_URL}/chat"
# The agent loads a local embedding model and makes several LLM calls, so the
# first request can take a while — keep a generous client-side timeout.
REQUEST_TIMEOUT_SECONDS = 120

_WELCOME_MESSAGE = (
    "Hello! I'm **LedgerMind**, your Infosys FY26 financial analyst.\n\n"
    "Ask me about quarterly results, the annual report, or share-price data. "
    "You can also ask me to **generate a PDF report** or **export data to Excel**."
)


def _init_session_state() -> None:
    """Seed the conversation with a welcome message on first load."""
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {"role": "assistant", "content": _WELCOME_MESSAGE}
        ]


def _query_backend(prompt: str) -> dict:
    """Send the query to the backend and return an assistant message dict.

    All network failures are caught and converted into a friendly assistant
    message so the UI degrades gracefully when the backend is unavailable.
    """
    try:
        response = requests.post(
            CHAT_ENDPOINT,
            json={"query": prompt},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()

        message: dict = {
            "role": "assistant",
            "content": data.get("answer", "_(the backend returned no answer)_"),
            "intent": data.get("intent", ""),
            "sources": data.get("sources", []),
        }
        # Backend returns a relative path; store the absolute URL for the link.
        file_url = data.get("file_url")
        if file_url:
            message["file_url"] = f"{BACKEND_URL}{file_url}"
        return message

    except requests.exceptions.ConnectionError:
        content = (
            ":warning: **Cannot reach the analysis backend.**\n\n"
            "Start the FastAPI server first — run `./scripts/run_server.sh` "
            "(or `uv run uvicorn backend.api.main:app`) so it is live at "
            "`http://localhost:8000`."
        )
    except requests.exceptions.Timeout:
        content = (
            ":warning: **The request timed out.** The analysis took longer "
            "than expected — please try again."
        )
    except requests.exceptions.HTTPError as exc:
        detail = str(exc)
        if exc.response is not None:
            try:
                detail = exc.response.json().get("detail", exc.response.text)
            except ValueError:
                detail = exc.response.text
        content = f":warning: **The backend returned an error.**\n\n{detail}"
    except requests.exceptions.RequestException as exc:
        content = f":warning: **Unexpected error contacting the backend.**\n\n{exc}"

    return {"role": "assistant", "content": content, "intent": "error"}


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
        "Multi-route agentic RAG over Infosys FY26 filings — "
        "narrative retrieval, quantitative analysis, and report generation."
    )

    render_chat_history()

    if prompt := st.chat_input("Ask about Infosys financials..."):
        # 1. Record and show the user's message.
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # 2-4. Call the backend behind a spinner.
        with st.chat_message("assistant"):
            with st.spinner("Analyzing financial data..."):
                assistant_message = _query_backend(prompt)
            st.markdown(assistant_message["content"])
            sources = assistant_message.get("sources", [])
            if sources:
                st.caption("📄 **Sources:** " + " · ".join(sources))
            file_url = assistant_message.get("file_url")
            if file_url:
                filename = file_url.rstrip("/").rsplit("/", 1)[-1] or "file"
                st.link_button(f"Download  {filename}", file_url)

        # 5-6. Persist the assistant message and refresh the UI.
        st.session_state.messages.append(assistant_message)
        st.rerun()


if __name__ == "__main__":
    main()
