"""Relevance selection for the generation context."""

from __future__ import annotations

import pytest

from novellire.core.context import (
    STORY_BIBLE_CHAR_LIMIT,
    GenerationContextBuilder,
)
from novellire.core.documents import ProjectDocumentService
from novellire.storage.document_repository import DocumentRepository
from novellire.storage.search_repository import SearchRepository
from novellire.storage.story_repositories import (
    ChapterRepository,
    CharacterRepository,
    StoryBibleRepository,
)


@pytest.fixture()
def context_builder(database, project_repository) -> GenerationContextBuilder:
    return GenerationContextBuilder(
        ProjectDocumentService(DocumentRepository(database), project_repository),
        StoryBibleRepository(database),
        CharacterRepository(database),
        ChapterRepository(database),
        SearchRepository(database),
    )


def test_build_selects_matching_canon_only(
    context_builder: GenerationContextBuilder,
    sample_project,
    story_bible_service,
    character_service,
    chapter_service,
) -> None:
    story_bible_service.create_entry(
        project_id=sample_project.id,
        category="premise",
        title="The sealed gate",
        content="The gate is bound with iron.",
    )
    story_bible_service.create_entry(
        project_id=sample_project.id,
        category="geography",
        title="The Southern Isles",
        content="A warm archipelago with no gates.",
    )
    mira = character_service.create_character(
        project_id=sample_project.id,
        name="Mira Voss",
        aliases=["the Courier"],
        personality="Watchful",
        secrets="She broke the seal once.",
    )
    character_service.create_character(
        project_id=sample_project.id,
        name="Orin Vale",
        personality="Dry.",
    )
    chapter = chapter_service.create_chapter(
        project_id=sample_project.id,
        title="Arrival",
        viewpoint_character_id=mira.id,
    )

    context = context_builder.build(
        sample_project.id,
        instructions="Mira reaches the gate.",
        chapter_id=chapter.id,
    )

    assert "The sealed gate" in context.bible_entries
    assert "The gate is bound with iron." in context.bible_entries
    assert "Southern Isles" not in context.bible_entries
    assert "Mira Voss" in context.character_profiles
    assert "the Courier" in context.character_profiles
    assert "Secrets: She broke the seal once." in context.character_profiles
    assert "Orin Vale" not in context.character_profiles


def test_build_retrieves_only_earlier_matching_chapters(
    context_builder: GenerationContextBuilder,
    sample_project,
    chapter_service,
) -> None:
    earlier = chapter_service.create_chapter(
        project_id=sample_project.id,
        title="The Gate",
        content="Mira crossed the ashen archive and read the ledger.",
        summary="Mira enters the archive and reads the ledger.",
    )
    current = chapter_service.create_chapter(
        project_id=sample_project.id, title="Return"
    )
    chapter_service.create_chapter(
        project_id=sample_project.id,
        title="Later",
        content="The archive burns.",
    )

    context = context_builder.build(
        sample_project.id,
        instructions="Mira returns to the ashen archive.",
        chapter_id=current.id,
    )

    assert [chapter.id for chapter in context.memory_chapters] == [earlier.id]
    assert context.memory_chapters[0].summary == (
        "Mira enters the archive and reads the ledger."
    )
    assert "archive" in context.memory_chapters[0].excerpt
    assert "Chapter 1 — The Gate" in context.earlier_chapters
    assert "Summary: Mira enters the archive" in context.earlier_chapters
    assert "Chapter 3 — Later" not in context.earlier_chapters
    assert context.earlier_chapters.count("Mira enters the archive") == 1


def test_build_omits_memory_when_the_request_names_nothing(
    context_builder: GenerationContextBuilder,
    sample_project,
    chapter_service,
) -> None:
    chapter_service.create_chapter(
        project_id=sample_project.id,
        title="The Gate",
        content="Mira crossed the archive.",
    )

    context = context_builder.build(
        sample_project.id, instructions="Continue the chapter."
    )

    assert context.memory_chapters == ()
    assert context.earlier_chapters == ""


def test_build_stays_within_the_story_bible_budget(
    context_builder: GenerationContextBuilder,
    sample_project,
    story_bible_service,
) -> None:
    for index in range(8):
        story_bible_service.create_entry(
            project_id=sample_project.id,
            category="world_building",
            title=f"Ash district {index}",
            content="ash " * 600,
        )

    context = context_builder.build(
        sample_project.id, instructions="Walk through the ash district."
    )

    assert context.bible_entries
    assert len(context.bible_entries) <= STORY_BIBLE_CHAR_LIMIT


def test_build_includes_a_small_cast_the_request_does_not_name(
    context_builder: GenerationContextBuilder,
    sample_project,
    character_service,
    chapter_service,
) -> None:
    character_service.create_character(
        project_id=sample_project.id,
        name="Mira Voss",
        personality="Watchful.",
    )
    chapter = chapter_service.create_chapter(
        project_id=sample_project.id, title="Arrival"
    )

    context = context_builder.build(
        sample_project.id,
        instructions="Write the next beat.",
        chapter_id=chapter.id,
    )

    assert "Mira Voss" in context.character_profiles
    assert "Personality: Watchful." in context.character_profiles
