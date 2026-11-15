"""Reusable, presentation-only Streamlit widgets."""

from __future__ import annotations

import streamlit as st

from ..core.settings_service import GenerationSettings
from ..llm.base import ModelInfo

_MANUAL_MODEL_HINT = (
    "Ollama reported no models. Enter a model name, or install one with "
    "`ollama pull qwen2.5:1.5b`."
)


def select_model(models: list[ModelInfo], current: str, *, key: str, label: str = "Model") -> str:
    """Render a model picker, falling back to a free-text field."""
    names = [model.name for model in models]
    if not names:
        return st.text_input(label, value=current, key=f"{key}_manual", help=_MANUAL_MODEL_HINT)

    index = names.index(current) if current in names else 0
    return st.selectbox(
        label,
        names,
        index=index,
        key=key,
        help="Models installed in Ollama. Only one model is loaded at a time.",
    )


def generation_parameter_inputs(
    settings: GenerationSettings, *, key_prefix: str
) -> tuple[float, float, int, int]:
    """Render generation controls and return the chosen values."""
    temperature = st.slider(
        "Temperature",
        min_value=0.0,
        max_value=2.0,
        value=float(settings.temperature),
        step=0.05,
        key=f"{key_prefix}_temperature",
        help="Lower is more consistent; higher is more varied.",
    )
    top_p = st.slider(
        "Top-p",
        min_value=0.05,
        max_value=1.0,
        value=float(settings.top_p),
        step=0.05,
        key=f"{key_prefix}_top_p",
    )
    num_predict = int(
        st.number_input(
            "Maximum output tokens",
            min_value=64,
            max_value=4096,
            value=int(settings.num_predict),
            step=64,
            key=f"{key_prefix}_num_predict",
        )
    )
    context_options = [2048, 4096, 8192]
    if settings.context_window not in context_options:
        context_options = sorted([*context_options, int(settings.context_window)])
    context_window = int(
        st.select_slider(
            "Context window (tokens)",
            options=context_options,
            value=int(settings.context_window)
            if settings.context_window in context_options
            else 4096,
            key=f"{key_prefix}_context_window",
            help="Larger windows use more RAM. 4096 is a safe default on 8 GB.",
        )
    )
    return temperature, top_p, num_predict, context_window


def format_size(size_bytes: int | None) -> str:
    if not size_bytes:
        return "unknown size"
    return f"{size_bytes / (1024 ** 3):.2f} GB"


def format_model_line(model: ModelInfo) -> str:
    details = ", ".join(
        part
        for part in (model.parameter_size, model.quantization, model.family)
        if part
    )
    suffix = f" ({details})" if details else ""
    return f"**{model.name}** — {format_size(model.size_bytes)}{suffix}"
