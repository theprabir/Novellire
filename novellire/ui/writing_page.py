"""Writing page: scene request, generation, and saved generation history."""

from __future__ import annotations

import streamlit as st

from ..core.settings_service import GenerationSettings
from ..errors import NovellireError
from ..logging_setup import get_logger
from ..storage.repositories import STATUS_FAILED
from .components import generation_parameter_inputs, select_model
from .runtime import AppContext, available_models, ollama_available

logger = get_logger("ui.writing")


def render(context: AppContext) -> None:
    st.header("Writing")

    project = context.projects.get_project(context.app_settings.active_project_id())
    if project is None:
        st.info("Select or create a project on the Projects page first.")
        return

    st.caption(f"Project: **{project.name}**")

    online = ollama_available()
    models = []
    if online:
        try:
            models = available_models()
        except NovellireError as exc:
            st.error(str(exc))

    if not online:
        st.error(
            f"Ollama is not reachable at {context.settings.ollama.base_url}. "
            "Start it with `ollama serve`, then reload this page."
        )
    elif not models:
        st.warning(
            "Ollama is running but reports no models. Install one with "
            "`ollama pull qwen2.5:1.5b`."
        )

    saved = context.app_settings.generation_settings()

    with st.container(border=True):
        model = select_model(models, saved.model, key="writing_model")
        with st.expander("Generation parameters", expanded=False):
            temperature, top_p, num_predict, context_window = generation_parameter_inputs(
                saved, key_prefix="writing"
            )

        chapter_title = st.text_input(
            "Chapter title (optional)", key="writing_chapter_title"
        )
        scene_title = st.text_input("Scene title (optional)", key="writing_scene_title")
        instructions = st.text_area(
            "What should happen in this scene?",
            height=140,
            key="writing_instructions",
            placeholder=(
                "Describe the beat: who is present, what changes, and what must be "
                "true by the end of the scene."
            ),
        )
        context_notes = st.text_area(
            "Context notes (optional)",
            height=90,
            key="writing_context_notes",
            placeholder="Any detail or constraint the model must honour.",
        )
        target_words = st.slider(
            "Target scene length (words)", min_value=200, max_value=2000, value=900, step=50
        )
        generate_clicked = st.button(
            "Generate scene",
            type="primary",
            disabled=not online,
            help=None if online else "Start Ollama to enable generation.",
        )

    if generate_clicked:
        settings = GenerationSettings(
            model=model,
            temperature=temperature,
            top_p=top_p,
            num_predict=num_predict,
            context_window=context_window,
        )
        try:
            context.app_settings.save_generation_settings(settings)
        except NovellireError as exc:
            st.error(str(exc))

        with st.spinner(f"Generating with {settings.model} — this can take a while on CPU."):
            try:
                outcome = context.generation.generate(
                    project_id=project.id,
                    instructions=instructions,
                    settings=settings,
                    chapter_title=chapter_title,
                    scene_title=scene_title,
                    context_notes=context_notes,
                    target_words=target_words,
                )
            except NovellireError as exc:
                st.error(str(exc))
            except Exception:  # noqa: BLE001 - surface a safe message, log details
                logger.exception("Unexpected generation failure")
                st.error(
                    "Generation failed unexpectedly. The detail was written to the "
                    "application log; your project data is unchanged."
                )
            else:
                st.session_state["writing_last_generation"] = outcome.record.id
                st.success(f"Saved {outcome.word_count:,} words to this project.")

    _render_history(context, project.id)


def _render_history(context: AppContext, project_id: int) -> None:
    records = context.generations.list_for_project(project_id, limit=25)
    if not records:
        st.caption("No generations saved for this project yet.")
        return

    st.subheader("Saved generations")
    labels = {
        f"#{record.id} · {record.created_at} · {record.model} · "
        f"{record.word_count:,} words · {record.status}": record.id
        for record in records
    }
    options = list(labels)
    last_id = st.session_state.get("writing_last_generation")
    default_index = next(
        (index for index, label in enumerate(options) if labels[label] == last_id), 0
    )
    choice = st.selectbox(
        "Generation history", options, index=default_index, key=f"history_{project_id}"
    )
    record = next(item for item in records if item.id == labels[choice])

    if record.status == STATUS_FAILED:
        st.warning(f"This attempt failed and produced no text: {record.error}")
        return

    seconds = record.duration_ms / 1000
    st.caption(
        f"{record.word_count:,} words · {record.model} · {seconds:.1f}s · "
        f"temperature {record.temperature:.2f} · top-p {record.top_p:.2f} · "
        f"max {record.num_predict} tokens · context {record.context_window}"
    )
    if record.truncated:
        st.warning(
            "The model reached its output token limit, so this scene may stop "
            "mid-thought. Raise the maximum output tokens and generate again."
        )
    st.text_area(
        "Generated text",
        value=record.output,
        height=420,
        key=f"generated_text_{record.id}",
        disabled=True,
        help="Draft editing and approval arrive in a later phase.",
    )
