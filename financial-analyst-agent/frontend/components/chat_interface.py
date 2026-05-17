"""Chat interface component for the LedgerMind Streamlit UI.

Replays the stored conversation, rendering each message in a chat bubble and
attaching a download control whenever the backend produced a file.
"""

from __future__ import annotations

import streamlit as st


def _render_download_link(file_url: str) -> None:
    """Render a download control for a backend-generated artifact.

    Args:
        file_url: Absolute URL to the file, e.g.
            ``http://localhost:8000/download/report.pdf``.
    """
    filename = file_url.rstrip("/").rsplit("/", 1)[-1] or "file"
    st.link_button(f"Download  {filename}", file_url, use_container_width=False)


def _render_sources(sources: list[str]) -> None:
    """Render the document(s) an answer was drawn from as an inline citation."""
    if sources:
        st.caption("📄 **Sources:** " + " · ".join(sources))


def render_chat_history() -> None:
    """Render every message currently held in ``st.session_state.messages``."""
    for message in st.session_state.get("messages", []):
        role = message.get("role", "assistant")
        with st.chat_message(role):
            st.markdown(message.get("content", ""))

            # Citation: the document(s) this answer drew from.
            _render_sources(message.get("sources", []))

            # If the backend attached a generated PDF/Excel, surface a download.
            file_url = message.get("file_url")
            if file_url:
                _render_download_link(file_url)
