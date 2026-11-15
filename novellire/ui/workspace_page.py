"""Workspace page: story bible, character profiles, chapter and scene structure."""

from __future__ import annotations

import streamlit as st

from ..core.characters import PROFILE_FIELDS
from ..core.story_bible import (
    CATEGORY_BY_LABEL,
    CATEGORY_LABELS,
    STORY_BIBLE_CATEGORIES,
)
from ..core.work_status import WORK_STATUSES, WORK_STATUS_LABELS
from ..errors import NovellireError
from ..storage.story_repositories import ChapterRecord, CharacterRecord
from .runtime import AppContext

_CATEGORY_OPTIONS = [label for _, label in STORY_BIBLE_CATEGORIES]
_STATUS_OPTIONS = [WORK_STATUS_LABELS[status] for status in WORK_STATUSES]
_STATUS_BY_LABEL = {WORK_STATUS_LABELS[status]: status for status in WORK_STATUSES}

_PROFILE_WIDGETS: tuple[tuple[str, str], ...] = (
    ("physical_description", "Physical description"),
    ("personality", "Personality"),
    ("motivations", "Motivations"),
    ("goals", "Goals"),
    ("fears", "Fears"),
    ("strengths", "Strengths"),
    ("weaknesses", "Weaknesses"),
    ("background", "Background"),
    ("secrets", "Secrets"),
    ("character_arc", "Character arc"),
)


def render(context: AppContext) -> None:
    st.header("Workspace")

    project = context.projects.get_project(context.app_settings.active_project_id())
    if project is None:
        st.info("Select or create a project on the Projects page first.")
        return

    st.caption(f"Project: **{project.name}**")
    bible_tab, characters_tab, chapters_tab = st.tabs(
        ["Story bible", "Characters", "Chapters"]
    )
    with bible_tab:
        _render_story_bible(context, project.id)
    with characters_tab:
        _render_characters(context, project.id)
    with chapters_tab:
        _render_chapters(context, project.id)


# -- story bible ----------------------------------------------------------


def _render_story_bible(context: AppContext, project_id: int) -> None:
    st.subheader("Story bible")
    st.caption(
        "Established world information. Search and retrieval across these entries "
        "arrive in a later phase."
    )

    with st.expander("Add an entry", expanded=False):
        with st.form("bible_add", clear_on_submit=True):
            category_label = st.selectbox(
                "Category", _CATEGORY_OPTIONS, key="bible_add_category"
            )
            title = st.text_input("Title", max_chars=200, key="bible_add_title")
            content = st.text_area("Content", height=150, key="bible_add_content")
            if st.form_submit_button("Add entry", type="primary"):
                try:
                    context.story_bible.create_entry(
                        project_id=project_id,
                        category=CATEGORY_BY_LABEL[category_label],
                        title=title,
                        content=content,
                    )
                except NovellireError as exc:
                    st.error(str(exc))
                else:
                    st.success("Entry added.")
                    st.rerun()

    filter_label = st.selectbox(
        "Filter by category", ["All categories", *_CATEGORY_OPTIONS], key="bible_filter"
    )
    category = (
        None if filter_label == "All categories" else CATEGORY_BY_LABEL[filter_label]
    )
    entries = context.story_bible.list_entries(project_id, category=category)
    if not entries:
        st.caption("No story bible entries yet.")
        return

    for entry in entries:
        with st.container(border=True):
            st.markdown(f"**{entry.title}** · {CATEGORY_LABELS[entry.category]}")
            if entry.content:
                preview = entry.content[:600]
                if len(entry.content) > 600:
                    preview += "…"
                st.write(preview)

    labels = {
        f"{entry.title} — {CATEGORY_LABELS[entry.category]}": entry.id
        for entry in entries
    }
    choice = st.selectbox("Edit an entry", list(labels), key="bible_edit_choice")
    entry = next(item for item in entries if item.id == labels[choice])
    category_index = _CATEGORY_OPTIONS.index(CATEGORY_LABELS[entry.category])

    with st.form(f"bible_edit_{entry.id}"):
        new_category = st.selectbox(
            "Category",
            _CATEGORY_OPTIONS,
            index=category_index,
            key=f"bible_edit_category_{entry.id}",
        )
        new_title = st.text_input(
            "Title", value=entry.title, max_chars=200, key=f"bible_edit_title_{entry.id}"
        )
        new_content = st.text_area(
            "Content",
            value=entry.content,
            height=220,
            key=f"bible_edit_content_{entry.id}",
        )
        if st.form_submit_button("Save entry"):
            try:
                context.story_bible.update_entry(
                    entry.id,
                    category=CATEGORY_BY_LABEL[new_category],
                    title=new_title,
                    content=new_content,
                )
            except NovellireError as exc:
                st.error(str(exc))
            else:
                st.success("Entry saved.")
                st.rerun()


# -- characters -----------------------------------------------------------


def _render_characters(context: AppContext, project_id: int) -> None:
    st.subheader("Characters")
    st.caption(
        "Stable identity information only. Current location, knowledge, and "
        "relationship state arrive with the narrative-state phase."
    )

    with st.expander("Add a character", expanded=False):
        with st.form("character_add", clear_on_submit=True):
            values = _character_form_fields({}, key_prefix="char_add")
            if st.form_submit_button("Add character", type="primary"):
                try:
                    context.characters.create_character(
                        project_id=project_id,
                        name=values.get("name", ""),
                        aliases=_split_aliases(values.get("aliases", "")),
                        **{field: values.get(field, "") for field in PROFILE_FIELDS},
                    )
                except NovellireError as exc:
                    st.error(str(exc))
                else:
                    st.success("Character added.")
                    st.rerun()

    characters = context.characters.list_characters(project_id)
    if not characters:
        st.caption("No characters yet.")
        return

    for character in characters:
        with st.container(border=True):
            heading = f"**{character.name}**"
            if character.aliases:
                heading += f" · aka {', '.join(character.aliases)}"
            st.markdown(heading)
            teaser = character.personality or character.background
            if teaser:
                st.caption(teaser[:200] + ("…" if len(teaser) > 200 else ""))

    labels = {character.name: character.id for character in characters}
    choice = st.selectbox("Edit a character", list(labels), key="character_edit_choice")
    character = next(item for item in characters if item.id == labels[choice])
    _render_character_editor(context, character)


def _render_character_editor(context: AppContext, character: CharacterRecord) -> None:
    prefix = f"char_edit_{character.id}"
    with st.form(prefix):
        values = {
            "name": character.name,
            "aliases": ", ".join(character.aliases),
            **{field: getattr(character, field) for field in PROFILE_FIELDS},
        }
        edited = _character_form_fields(values, key_prefix=prefix)
        if st.form_submit_button("Save character"):
            try:
                context.characters.update_character(
                    character.id,
                    name=edited.get("name", ""),
                    **{field: edited.get(field, "") for field in PROFILE_FIELDS},
                )
                context.characters.set_aliases(
                    character.id, _split_aliases(edited.get("aliases", ""))
                )
            except NovellireError as exc:
                st.error(str(exc))
            else:
                st.success("Character saved.")
                st.rerun()


def _character_form_fields(
    values: dict[str, str], *, key_prefix: str
) -> dict[str, str]:
    """Render the character form fields and return their current values."""
    collected: dict[str, str] = {
        "name": st.text_input(
            "Name",
            value=values.get("name", ""),
            max_chars=120,
            key=f"{key_prefix}_name",
        ),
        "aliases": st.text_input(
            "Aliases (comma separated)",
            value=values.get("aliases", ""),
            key=f"{key_prefix}_aliases",
        ),
        "age": st.text_input(
            "Age or age range",
            value=values.get("age", ""),
            key=f"{key_prefix}_age",
        ),
    }

    left, right = st.columns(2)
    for index, (field, label) in enumerate(_PROFILE_WIDGETS):
        target = left if index % 2 == 0 else right
        collected[field] = target.text_area(
            label,
            value=values.get(field, ""),
            height=80,
            key=f"{key_prefix}_{field}",
        )

    return collected


def _split_aliases(text: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in (text or "").split(",") if part.strip())


# -- chapters and scenes --------------------------------------------------


def _render_chapters(context: AppContext, project_id: int) -> None:
    st.subheader("Chapter map")
    characters = context.characters.list_characters(project_id)
    viewpoint_labels = ["No viewpoint set", *[character.name for character in characters]]
    viewpoint_ids = {character.name: character.id for character in characters}

    with st.expander("Add a chapter", expanded=False):
        with st.form("chapter_add", clear_on_submit=True):
            title = st.text_input(
                "Chapter title", max_chars=200, key="chapter_add_title"
            )
            part = st.text_input(
                "Part or act (optional)", max_chars=120, key="chapter_add_part"
            )
            summary = st.text_area("Summary", height=80, key="chapter_add_summary")
            objectives = st.text_area(
                "Objectives and required developments",
                height=90,
                key="chapter_add_objectives",
            )
            viewpoint_label = st.selectbox(
                "Viewpoint character",
                viewpoint_labels,
                key="chapter_add_viewpoint",
            )
            target = st.number_input(
                "Target words (optional)",
                min_value=0,
                max_value=100_000,
                value=0,
                step=500,
                key="chapter_add_target",
            )
            if st.form_submit_button("Add chapter", type="primary"):
                try:
                    context.chapters.create_chapter(
                        project_id=project_id,
                        title=title,
                        part=part,
                        summary=summary,
                        objectives=objectives,
                        viewpoint_character_id=viewpoint_ids.get(viewpoint_label),
                        target_word_count=int(target) or None,
                    )
                except NovellireError as exc:
                    st.error(str(exc))
                else:
                    st.success("Chapter added.")
                    st.rerun()

    chapters = context.chapters.list_chapters(project_id)
    if not chapters:
        st.caption("No chapters yet. Add the first chapter above.")
        return

    for chapter in chapters:
        words = context.scenes.total_words(chapter.id)
        with st.container(border=True):
            st.markdown(
                f"**{chapter.position}. {chapter.title}** · "
                f"{WORK_STATUS_LABELS[chapter.status]} · {words:,} words"
            )
            meta = [part for part in [chapter.part] if part]
            if chapter.target_word_count:
                meta.append(f"target {chapter.target_word_count:,}")
            if meta:
                st.caption(" · ".join(meta))
            if chapter.summary:
                st.write(chapter.summary[:400])

    labels = {
        f"{chapter.position}. {chapter.title}": chapter.id for chapter in chapters
    }
    choice = st.selectbox("Select a chapter", list(labels), key="chapter_choice")
    chapter = next(item for item in chapters if item.id == labels[choice])

    _render_chapter_editor(context, chapter, viewpoint_labels, viewpoint_ids)
    _render_scenes(context, chapter.id)


def _render_chapter_editor(
    context: AppContext,
    chapter: ChapterRecord,
    viewpoint_labels: list[str],
    viewpoint_ids: dict[str, int],
) -> None:
    prefix = f"chapter_edit_{chapter.id}"
    current_viewpoint = next(
        (
            label
            for label, character_id in viewpoint_ids.items()
            if character_id == chapter.viewpoint_character_id
        ),
        "No viewpoint set",
    )

    with st.form(prefix):
        title = st.text_input(
            "Chapter title",
            value=chapter.title,
            max_chars=200,
            key=f"{prefix}_title",
        )
        part = st.text_input(
            "Part or act", value=chapter.part, max_chars=120, key=f"{prefix}_part"
        )
        summary = st.text_area(
            "Summary", value=chapter.summary, height=90, key=f"{prefix}_summary"
        )
        objectives = st.text_area(
            "Objectives and required developments",
            value=chapter.objectives,
            height=100,
            key=f"{prefix}_objectives",
        )
        status_label = st.selectbox(
            "Status",
            _STATUS_OPTIONS,
            index=_STATUS_OPTIONS.index(WORK_STATUS_LABELS[chapter.status]),
            key=f"{prefix}_status",
        )
        viewpoint_label = st.selectbox(
            "Viewpoint character",
            viewpoint_labels,
            index=viewpoint_labels.index(current_viewpoint),
            key=f"{prefix}_viewpoint",
        )
        target = st.number_input(
            "Target words",
            min_value=0,
            max_value=100_000,
            value=int(chapter.target_word_count or 0),
            step=500,
            key=f"{prefix}_target",
        )
        if st.form_submit_button("Save chapter"):
            try:
                context.chapters.update_chapter(
                    chapter.id,
                    title=title,
                    part=part,
                    summary=summary,
                    objectives=objectives,
                    status=_STATUS_BY_LABEL[status_label],
                    viewpoint_character_id=viewpoint_ids.get(viewpoint_label),
                    target_word_count=int(target) or None,
                )
            except NovellireError as exc:
                st.error(str(exc))
            else:
                st.success("Chapter saved.")
                st.rerun()


def _render_scenes(context: AppContext, chapter_id: int) -> None:
    st.markdown("**Scenes**")
    scenes = context.scenes.list_scenes(chapter_id)

    if scenes:
        for scene in scenes:
            with st.container(border=True):
                heading = f"**{scene.position}. {scene.title or 'Untitled scene'}**"
                heading += (
                    f" · {WORK_STATUS_LABELS[scene.status]} · {scene.word_count:,} words"
                )
                st.markdown(heading)
                if scene.summary:
                    st.caption(scene.summary[:300])
    else:
        st.caption("No scenes in this chapter yet.")

    add_prefix = f"scene_add_{chapter_id}"
    with st.expander("Add a scene", expanded=False):
        with st.form(add_prefix, clear_on_submit=True):
            title = st.text_input(
                "Scene title (optional)", max_chars=200, key=f"{add_prefix}_title"
            )
            summary = st.text_area("Summary", height=70, key=f"{add_prefix}_summary")
            objectives = st.text_area(
                "Objectives", height=70, key=f"{add_prefix}_objectives"
            )
            content = st.text_area(
                "Draft text (optional)", height=160, key=f"{add_prefix}_content"
            )
            status_label = st.selectbox(
                "Status", _STATUS_OPTIONS, index=0, key=f"{add_prefix}_status"
            )
            if st.form_submit_button("Add scene"):
                try:
                    context.scenes.create_scene(
                        chapter_id,
                        title=title,
                        summary=summary,
                        objectives=objectives,
                        content=content,
                        status=_STATUS_BY_LABEL[status_label],
                    )
                except NovellireError as exc:
                    st.error(str(exc))
                else:
                    st.success("Scene added.")
                    st.rerun()

    if not scenes:
        return

    labels = {
        f"{scene.position}. {scene.title or 'Untitled scene'}": scene.id
        for scene in scenes
    }
    choice = st.selectbox(
        "Edit a scene", list(labels), key=f"scene_choice_{chapter_id}"
    )
    scene = next(item for item in scenes if item.id == labels[choice])

    prefix = f"scene_edit_{scene.id}"
    with st.form(prefix):
        title = st.text_input(
            "Scene title", value=scene.title, max_chars=200, key=f"{prefix}_title"
        )
        summary = st.text_area(
            "Summary", value=scene.summary, height=80, key=f"{prefix}_summary"
        )
        objectives = st.text_area(
            "Objectives", value=scene.objectives, height=80, key=f"{prefix}_objectives"
        )
        content = st.text_area(
            "Scene text", value=scene.content, height=320, key=f"{prefix}_content"
        )
        status_label = st.selectbox(
            "Status",
            _STATUS_OPTIONS,
            index=_STATUS_OPTIONS.index(WORK_STATUS_LABELS[scene.status]),
            key=f"{prefix}_status",
        )
        if st.form_submit_button("Save scene"):
            try:
                context.scenes.update_scene(
                    scene.id,
                    title=title,
                    summary=summary,
                    objectives=objectives,
                    content=content,
                    status=_STATUS_BY_LABEL[status_label],
                )
            except NovellireError as exc:
                st.error(str(exc))
            else:
                st.success("Scene saved.")
                st.rerun()
