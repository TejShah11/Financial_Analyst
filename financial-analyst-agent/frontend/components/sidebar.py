"""Sidebar component for the LedgerMind Streamlit UI.

Renders the app identity, the knowledge-base contents the user can ask about,
and a control to reset the conversation.
"""

from __future__ import annotations

import streamlit as st

# Documents indexed by the backend — shown so users know the answerable scope.
_KNOWLEDGE_BASE = [
    "Q1 FY26 — IFRS USD earnings press release",
    "Q2 FY26 — IFRS USD earnings press release",
    "Q3 FY26 — IFRS USD earnings press release",
    "Q4 FY26 — IFRS USD earnings press release",
    "Infosys Annual Report (FY25)",
    "Daily share-price history (CSV)",
    "Investor data sheet (XLS)",
]


def render_sidebar() -> None:
    """Render the application sidebar."""
    with st.sidebar:
        st.title("LedgerMind Core")
        st.caption(
            "An agentic financial analyst — multi-route RAG powered by "
            "LangGraph and Google Gemini."
        )

        st.divider()
        st.subheader("Knowledge base")
        st.markdown("Ask questions grounded in these Infosys FY26 documents:")
        for document in _KNOWLEDGE_BASE:
            st.markdown(f"- {document}")

        st.divider()
        st.subheader("Tips")
        st.markdown(
            "- Ask for narrative insight *or* exact figures.\n"
            "- Say **\"export to Excel\"** or **\"generate a PDF report\"** "
            "to download a file."
        )

        st.divider()
        if st.button("Clear Conversation", use_container_width=True):
            # Drop the history so app.py re-seeds the welcome message on rerun.
            st.session_state.pop("messages", None)
            st.rerun()
