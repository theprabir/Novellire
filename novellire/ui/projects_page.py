"""Projects page: overview, creation, selection, and archival."""

from __future__ import annotations

import streamlit as st

from ..errors import NovellireError
from ..storage.repositories import Project
from .runtime import AppContext, ollama_available

_CREATE_FORM = "create_project"


def render(context: AppContext) -> None:
    st.header("Projects")

    projects = context.projects.list_projects()
    active = context.projects.get_project(context.app_settings.active_project_id())

    _render_overview(context, projects, active)
    _render_create_form(context)

    st.subheader("Your projects")
    if not projects:
        st.info("No projects yet. Create your first project above.")
        return

    for project in projects:
        _render_project_row(
            context,
            project,
            is_active=active is not None and active.id == project.id,
        )


def _render_overview(
    context: AppContext, projects: list[Project], active: Project | None
) -> None:
    columns = st.columns(4)
    columns[0].metric("Projects", len(projects))
    columns[1].metric("Active project", active.name if active else "None")
    if active is not None:
        columns[2].metric(
            "Words generated", f"{context.generations.produced_words(active.id):,}"
        )
        attempts = context.generations.count_for_project(active.id)
        columns[3].metric("Generations", attempts)
    else:
        columns[2].metric("Words generated", "—")
        columns[3].metric("Generations", "—")

    if ollama_available():
        st.caption(f"Ollama connected at `{context.settings.ollama.base_url}`")
    else:
        st.caption(
            f"Ollama offline at `{context.settings.ollama.base_url}` — start it with "
            "`ollama serve` before generating."
        )


def _render_create_form(context: AppContext) -> None:
    with st.form(_CREATE_FORM, clear_on_submit=True):
        st.markdown("**New project**")
        name = st.text_input("Project name", max_chars=120, placeholder="The Ashfall Chronicle")
        description = st.text_area(
            "Premise",
            height=90,
            placeholder="One or two sentences about the story.",
        )
        left, right = st.columns(2)
        genre = left.text_input("Genre", placeholder="Science fiction")
        narrative_style = right.text_input(
            "Narrative style", placeholder="Close third person, past tense"
        )
        target = st.number_input(
            "Target word count",
            min_value=0,
            max_value=20_000_000,
            value=80_000,
            step=1_000,
            help="Leave at 0 to skip setting a target.",
        )
        submitted = st.form_submit_button("Create project", type="primary")

    if not submitted:
        return

    try:
        project = context.projects.create_project(
            name=name,
            description=description,
            genre=genre,
            narrative_style=narrative_style,
            target_word_count=int(target) or None,
        )
    except NovellireError as exc:
        st.error(str(exc))
        return

    context.app_settings.set_active_project_id(project.id)
    st.success(f"Created '{project.name}' and set it as the active project.")
    st.rerun()


def _render_project_row(context: AppContext, project: Project, *, is_active: bool) -> None:
    with st.container(border=True):
        details, actions = st.columns([3, 1])
        title = f"**{project.name}**" + (" — *active*" if is_active else "")
        details.markdown(title)

        words = context.generations.produced_words(project.id)
        meta = [project.genre or "No genre set", f"{words:,} words generated"]
        if project.target_word_count:
            meta.append(f"target {project.target_word_count:,}")
        details.caption(" · ".join(meta))

        if project.description:
            details.write(project.description)

        if is_active:
            actions.caption("Selected for writing")
        elif actions.button(
            "Open", key=f"open_project_{project.id}", use_container_width=True
        ):
            context.app_settings.set_active_project_id(project.id)
            st.rerun()

        if actions.button(
            "Archive", key=f"archive_project_{project.id}", use_container_width=True
        ):
            try:
                context.projects.archive_project(project.id)
            except NovellireError as exc:
                st.error(str(exc))
                return
            if is_active:
                context.app_settings.set_active_project_id(None)
            st.rerun()
