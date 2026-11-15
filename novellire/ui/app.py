"""Streamlit application shell: sidebar navigation and page dispatch."""

from __future__ import annotations

import streamlit as st

from ..errors import NovellireError
from ..logging_setup import get_logger
from .projects_page import render as render_projects
from .runtime import AppContext, get_context, ollama_available
from .settings_page import render as render_settings
from .writing_page import render as render_writing

logger = get_logger("ui.app")

_PAGES = ("Projects", "Writing", "Settings")


def main() -> None:
    st.set_page_config(
        page_title="Novellire",
        page_icon="🖋",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    try:
        context = get_context()
    except NovellireError as exc:
        st.error(f"Novellire could not start: {exc}")
        st.stop()
        return

    page = _render_sidebar(context)
    if page == "Writing":
        render_writing(context)
    elif page == "Settings":
        render_settings(context)
    else:
        render_projects(context)


def _render_sidebar(context: AppContext) -> str:
    sidebar = st.sidebar
    sidebar.title("Novellire")
    sidebar.caption("Local-first novel workspace")

    page = sidebar.radio("Go to", _PAGES, key="nav_page")

    sidebar.divider()
    active = context.projects.get_project(context.app_settings.active_project_id())
    if active is None:
        sidebar.caption("No active project")
    else:
        sidebar.markdown(f"**Active project**  \n{active.name}")

    saved_model = context.app_settings.generation_settings().model
    sidebar.markdown(f"**Model**  \n{saved_model or 'not set'}")
    sidebar.caption(
        "Ollama: connected" if ollama_available() else "Ollama: offline"
    )
    return page
