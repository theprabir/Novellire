"""Relevance selection for the generation context."""

from __future__ import annotations

import pytest

from novellire.core.context import (
    STORY_BIBLE_CHAR_LIMIT,
    GenerationContextBuilder,
)
from novellire.core.documents import ProjectDocumentService
from novellire.storage.document_repository import DocumentRepository
from novellire.storage.event_repository import EventDraft, EventRepository
from novellire.storage.relationship_repository import RelationshipRepository
from novellire.storage.search_repository import SearchRepository
from novellire.storage.state_repository import CharacterStateRepository
from novellire.storage.story_repositories import (
    ChapterRepository,
    CharacterRepository,
    StoryBibleRepository,
)


@pytest.fixture()
def event_repository(database) -> EventRepository:
    return EventRepository(database)


@pytest.fixture()
def context_builder(
    database, project_repository, event_repository
) -> GenerationContextBuilder:
    return GenerationContextBuilder(
        ProjectDocumentService(DocumentRepository(database), project_repository),
        StoryBibleRepository(database),
        CharacterRepository(database),
        ChapterRepository(database),
        SearchRepository(database),
        event_repository,
        RelationshipRepository(database),
        CharacterStateRepository(database),
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
        objectives="1. Mira reaches the gate.\n2. The gate opens.",
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
    assert "1. Mira reaches the gate." in context.chapter_plan


def test_build_includes_only_approved_relationships_for_selected_profiles(
    context_builder: GenerationContextBuilder,
    database,
    sample_project,
    character_service,
) -> None:
    mira = character_service.create_character(
        project_id=sample_project.id, name="Mira Voss"
    )
    orin = character_service.create_character(
        project_id=sample_project.id, name="Orin Vale"
    )
    keeper = character_service.create_character(
        project_id=sample_project.id, name="The Keeper"
    )
    relationships = RelationshipRepository(database)
    relationships.create(
        project_id=sample_project.id,
        character_a_id=mira.id,
        character_b_id=orin.id,
        relation_type="ally",
        description="They guard the archive together.",
        status="approved",
        source_event_id=None,
    )
    relationships.create(
        project_id=sample_project.id,
        character_a_id=mira.id,
        character_b_id=keeper.id,
        relation_type="rival",
        description="An uneasy truce.",
        status="proposed",
        source_event_id=None,
    )

    context = context_builder.build(
        sample_project.id, instructions="Mira meets Orin at the gate."
    )

    assert "Mira Voss — Orin Vale: Ally" in context.relationship_records
    assert "They guard the archive together." in context.relationship_records
    assert "The Keeper" not in context.relationship_records


def test_build_omits_rejected_relationships(
    context_builder: GenerationContextBuilder,
    database,
    sample_project,
    character_service,
) -> None:
    mira = character_service.create_character(
        project_id=sample_project.id, name="Mira Voss"
    )
    orin = character_service.create_character(
        project_id=sample_project.id, name="Orin Vale"
    )
    RelationshipRepository(database).create(
        project_id=sample_project.id,
        character_a_id=mira.id,
        character_b_id=orin.id,
        relation_type="family",
        description="Rejected in review.",
        status="rejected",
        source_event_id=None,
    )

    context = context_builder.build(
        sample_project.id, instructions="Mira meets Orin at the gate."
    )

    assert context.relationship_records == ""


def test_build_includes_only_current_state_for_selected_profiles(
    context_builder: GenerationContextBuilder,
    database,
    sample_project,
    character_service,
    chapter_service,
) -> None:
    mira = character_service.create_character(
        project_id=sample_project.id, name="Mira Voss"
    )
    keeper = character_service.create_character(
        project_id=sample_project.id, name="The Keeper"
    )
    first = chapter_service.create_chapter(
        project_id=sample_project.id, title="Part One"
    )
    second = chapter_service.create_chapter(
        project_id=sample_project.id, title="Part Two"
    )
    states = CharacterStateRepository(database)
    states.create(
        project_id=sample_project.id,
        character_id=mira.id,
        chapter_id=first.id,
        location="The archive",
        status="Wounded",
        goals="Reach the gate",
        knowledge="She knows the gate is warded",
    )
    states.create(
        project_id=sample_project.id,
        character_id=mira.id,
        chapter_id=second.id,
        location="The keep",
        status="Recovering",
        goals="Find the ledger",
        knowledge="She knows Orin has the key",
    )

    context = context_builder.build(
        sample_project.id, instructions="Mira searches the keep for Orin."
    )

    assert "Mira Voss (as of Chapter 2 — Part Two)" in context.character_states
    assert "Location: The keep" in context.character_states
    assert "Knowledge: She knows Orin has the key" in context.character_states
    assert "The archive" not in context.character_states
    assert "The Keeper" not in context.character_states


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


def test_build_retrieves_matching_events_from_earlier_chapters(
    context_builder: GenerationContextBuilder,
    event_repository: EventRepository,
    sample_project,
    chapter_service,
) -> None:
    earlier = chapter_service.create_chapter(
        project_id=sample_project.id,
        title="The Gate",
        content="Mira crossed the ashen archive.",
    )
    current = chapter_service.create_chapter(
        project_id=sample_project.id, title="Return"
    )
    later = chapter_service.create_chapter(
        project_id=sample_project.id, title="After", content="The archive burns."
    )
    event_repository.replace_for_chapter(
        sample_project.id,
        earlier.id,
        [
            EventDraft(
                summary="Mira hides the sealed key beneath her coat.",
                characters=("Mira",),
                locations=("archive",),
                objects=("sealed key",),
                threads=("Who sealed the ledger?",),
            )
        ],
        model="fake-model",
    )
    event_repository.replace_for_chapter(
        sample_project.id,
        current.id,
        [EventDraft(summary="Mira returns to the archive.")],
        model="fake-model",
    )
    event_repository.replace_for_chapter(
        sample_project.id,
        later.id,
        [EventDraft(summary="The archive burns in the archive.")],
        model="fake-model",
    )

    context = context_builder.build(
        sample_project.id,
        instructions="Mira returns to the ashen archive.",
        chapter_id=current.id,
    )

    assert len(context.memory_events) == 1
    event = context.memory_events[0]
    assert event.chapter_id == earlier.id
    assert event.chapter_position == 1
    assert event.characters == ("Mira",)
    assert "Chapter 1 — The Gate" in context.earlier_events
    assert "Event: Mira hides the sealed key" in context.earlier_events
    assert "Characters: Mira" in context.earlier_events
    assert "Chapter 2 — Return" not in context.earlier_events
    assert "Chapter 3 — After" not in context.earlier_events


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
    assert context.memory_events == ()
    assert context.earlier_chapters == ""
    assert context.earlier_events == ""


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
