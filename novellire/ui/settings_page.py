"""Settings page: Ollama status, model configuration, and application info."""

from __future__ import annotations

import platform

import streamlit as st

from ..core.settings_service import GenerationSettings
from ..errors import NovellireError
from .components import (
    format_model_line,
    generation_parameter_inputs,
    select_model,
)
from .runtime import (
    AppContext,
    available_models,
    ollama_available,
    refresh_provider_state,
)


def render(context: AppContext) -> None:
    st.header("Settings")
    _render_connection(context)
    _render_models(context)
    _render_generation_defaults(context)
    _render_application_info(context)


def _render_connection(context: AppContext) -> None:
    st.subheader("Ollama connection")
    online = ollama_available()

    status, action = st.columns([3, 1])
    if online:
        status.success("Connected")
    else:
        status.error("Offline — start Ollama with `ollama serve`")

    status.markdown(f"Endpoint: `{context.settings.ollama.base_url}`")
    status.caption(
        "Configured through `config.toml` or the `NOVELLIRE_OLLAMA_URL` "
        "environment variable. Restart the app after changing it."
    )
    if action.button("Test connection", use_container_width=True):
        refresh_provider_state()
        st.rerun()


def _render_models(context: AppContext) -> None:
    st.subheader("Installed models")
    if not ollama_available():
        st.caption("Connect to Ollama to list models.")
        return
    try:
        models = available_models()
    except NovellireError as exc:
        st.error(str(exc))
        return
    if not models:
        st.info(
            "No models installed. Run `ollama pull qwen2.5:1.5b` in a terminal, "
            "then press Test connection."
        )
        return
    for model in models:
        st.markdown(f"- {format_model_line(model)}")
    st.caption(
        "Only one model is loaded at a time. Larger models need more RAM than "
        "their download size suggests."
    )


def _render_generation_defaults(context: AppContext) -> None:
    st.subheader("Default generation settings")
    saved = context.app_settings.generation_settings()
    models = []
    if ollama_available():
        try:
            models = available_models()
        except NovellireError:
            models = []

    with st.form("generation_defaults"):
        model = select_model(models, saved.model, key="settings_model")
        temperature, top_p, num_predict, context_window = generation_parameter_inputs(
            saved, key_prefix="settings"
        )
        submitted = st.form_submit_button("Save defaults", type="primary")

    if not submitted:
        return

    try:
        context.app_settings.save_generation_settings(
            GenerationSettings(
                model=model,
                temperature=temperature,
                top_p=top_p,
                num_predict=num_predict,
                context_window=context_window,
            )
        )
    except NovellireError as exc:
        st.error(str(exc))
    else:
        st.success("Defaults saved. The Writing page now starts from these values.")


def _render_application_info(context: AppContext) -> None:
    st.subheader("Application")
    st.markdown(
        f"- Data directory: `{context.settings.data_dir}`\n"
        f"- Database: `{context.database.path}`\n"
        f"- Schema version: `{context.database.schema_version()}`\n"
        f"- Python: `{platform.python_version()}`"
    )
    st.caption(
        "All inference is local. Novellire makes no cloud requests and sends no "
        "project content anywhere."
    )
