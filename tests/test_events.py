"""Episodic event extraction, validation, and provenance."""

from __future__ import annotations

import json

import pytest

from novellire.core.events import EventExtractionService, parse_event_payload
from novellire.core.settings_service import GenerationSettings
from novellire.errors import InvalidInputError, LLMResponseError
from novellire.llm.base import GenerationResult
from novellire.storage.event_repository import EventDraft, EventRepository
from novellire.storage.story_repositories import CharacterRepository


@pytest.fixture()
def event_repository(database) -> EventRepository:
    return EventRepository(database)


@pytest.fixture()
def event_service(
    database,
    fake_provider,
    project_repository,
    chapter_service,
    event_repository,
) -> EventExtractionService:
    return EventExtractionService(
        fake_provider,
        project_repository,
        chapter_service,
        event_repository,
        CharacterRepository(database),
    )


def _payload() -> str:
    return json.dumps(
        {
            "events": [
                {
                    "summary": "Mira reaches the archive and meets the keeper.",
                    "characters": ["Mira", "the keeper"],
                    "locations": ["archive"],
                    "objects": ["sealed key", "ledger"],
                    "threads": ["Why does the keeper guard the ledger?"],
                },
                {
                    "summary": "Mira hides the key in her coat.",
                    "characters": ["Mira"],
                    "locations": ["archive"],
                    "objects": ["sealed key"],
                    "threads": [],
                },
            ]
        }
    )


def test_parse_accepts_fenced_json_and_cleans_fields() -> None:
    text = (
        "```json\n"
        + json.dumps(
            {
                "events": [
                    {
                        "summary": "  Mira   enters the archive. ",
                        "characters": ["Mira", "Mira", ""],
                        "locations": "not-a-list",
                        "objects": ["key"],
                        "threads": ["Who sealed it?"],
                    }
                ]
            }
        )
        + "\n```"
    )

    drafts = parse_event_payload(text)

    assert len(drafts) == 1
    assert drafts[0].summary == "Mira enters the archive."
    assert drafts[0].characters == ("Mira",)
    assert drafts[0].locations == ()
    assert drafts[0].threads == ("Who sealed it?",)


def test_parse_rejects_malformed_json() -> None:
    with pytest.raises(LLMResponseError, match="malformed"):
        parse_event_payload('{"events": [}')


def test_extraction_stores_events_with_chapter_provenance(
    event_service: EventExtractionService,
    event_repository: EventRepository,
    chapter_service,
    fake_provider,
    sample_project,
) -> None:
    chapter = chapter_service.create_chapter(
        project_id=sample_project.id,
        title="The Gate",
        content="Mira crossed the ashen archive and met the keeper.",
    )
    fake_provider.result = GenerationResult(
        text=_payload(), model="fake-model", duration_ms=77
    )

    outcome = event_service.extract(
        chapter.id, GenerationSettings(model="fake-model")
    )

    assert outcome.duration_ms == 77
    assert len(outcome.events) == 2
    stored = event_repository.list_for_project(sample_project.id)
    assert [event.summary for event in stored] == [
        "Mira reaches the archive and meets the keeper.",
        "Mira hides the key in her coat.",
    ]
    assert stored[0].chapter_id == chapter.id
    assert stored[0].chapter_title == "The Gate"
    assert stored[0].chapter_position == 1
    assert stored[0].characters == ("Mira", "the keeper")
    assert stored[0].objects == ("sealed key", "ledger")
    assert stored[0].threads == ("Why does the keeper guard the ledger?",)
    assert stored[0].model == "fake-model"
    assert "ashen archive" in fake_provider.requests[0].prompt
    assert "Between 1 and 8 events" in fake_provider.requests[0].prompt


def test_links_character_profiles_by_name_and_alias(
    event_service: EventExtractionService,
    event_repository: EventRepository,
    character_service,
    chapter_service,
    sample_project,
) -> None:
    mira = character_service.create_character(
        project_id=sample_project.id,
        name="Mira Voss",
        aliases=["the Courier"],
    )
    orin = character_service.create_character(
        project_id=sample_project.id, name="Orin Vale"
    )
    chapter = chapter_service.create_chapter(
        project_id=sample_project.id,
        title="The Gate",
        content="Mira crosses the archive.",
    )
    event_repository.replace_for_chapter(
        sample_project.id,
        chapter.id,
        [
            EventDraft(
                summary="Mira reaches the archive.", characters=("Mira",)
            ),
            EventDraft(
                summary="The Courier leaves.", characters=("the Courier",)
            ),
            EventDraft(summary="Unrelated errand.", characters=()),
        ],
        model="fake-model",
    )

    event_service.ensure_links(sample_project.id)

    events = event_repository.list_for_chapter(chapter.id)
    by_summary = {event.summary: event for event in events}
    assert mira.id in by_summary["Mira reaches the archive."].character_ids
    assert mira.id in by_summary["The Courier leaves."].character_ids
    assert orin.id not in by_summary["Mira reaches the archive."].character_ids
    assert by_summary["Unrelated errand."].character_ids == ()


def test_extraction_links_characters_immediately(
    event_service: EventExtractionService,
    event_repository: EventRepository,
    character_service,
    chapter_service,
    fake_provider,
    sample_project,
) -> None:
    mira = character_service.create_character(
        project_id=sample_project.id,
        name="Mira Voss",
        aliases=["the Courier"],
    )
    chapter = chapter_service.create_chapter(
        project_id=sample_project.id, title="The Gate", content="Mira enters."
    )
    fake_provider.result = GenerationResult(
        text=_payload(), model="fake-model", duration_ms=10
    )

    outcome = event_service.extract(
        chapter.id, GenerationSettings(model="fake-model")
    )

    assert mira.id in outcome.events[0].character_ids
    assert mira.id in event_repository.list_for_chapter(chapter.id)[1].character_ids


def test_editing_an_event_updates_fields_and_links(
    event_service: EventExtractionService,
    event_repository: EventRepository,
    character_service,
    chapter_service,
    sample_project,
) -> None:
    mira = character_service.create_character(
        project_id=sample_project.id, name="Mira Voss"
    )
    orin = character_service.create_character(
        project_id=sample_project.id, name="Orin Vale"
    )
    chapter = chapter_service.create_chapter(
        project_id=sample_project.id,
        title="The Gate",
        content="Mira crosses the archive.",
    )
    event_repository.replace_for_chapter(
        sample_project.id,
        chapter.id,
        [EventDraft(summary="Mira reaches the archive.", characters=("Mira",))],
        model="fake-model",
    )
    event = event_repository.list_for_chapter(chapter.id)[0]

    updated = event_service.update_event(
        event.id,
        summary="Orin takes the ledger instead.",
        characters=["Orin"],
        locations=["keep"],
        objects=["ledger"],
        threads=[],
    )

    assert updated.summary == "Orin takes the ledger instead."
    assert updated.locations == ("keep",)
    assert orin.id in updated.character_ids
    assert mira.id not in updated.character_ids


def test_deleting_an_event_removes_it(
    event_service: EventExtractionService,
    event_repository: EventRepository,
    chapter_service,
    sample_project,
) -> None:
    chapter = chapter_service.create_chapter(
        project_id=sample_project.id,
        title="The Gate",
        content="Mira crosses the archive.",
    )
    event_repository.replace_for_chapter(
        sample_project.id,
        chapter.id,
        [EventDraft(summary="Mira reaches the archive.", characters=("Mira",))],
        model="fake-model",
    )
    event = event_repository.list_for_chapter(chapter.id)[0]

    event_service.delete_event(event.id)

    assert event_repository.get(event.id) is None


def test_extraction_replaces_previous_events_for_the_chapter(
    event_service: EventExtractionService,
    event_repository: EventRepository,
    chapter_service,
    fake_provider,
    sample_project,
) -> None:
    chapter = chapter_service.create_chapter(
        project_id=sample_project.id, title="The Gate", content="Mira enters."
    )
    fake_provider.result = GenerationResult(
        text=_payload(), model="fake-model", duration_ms=10
    )
    event_service.extract(chapter.id, GenerationSettings(model="fake-model"))

    fake_provider.result = GenerationResult(
        text=json.dumps(
            {
                "events": [
                    {
                        "summary": "Mira leaves the archive.",
                        "characters": ["Mira"],
                        "locations": ["archive"],
                        "objects": [],
                        "threads": [],
                    }
                ]
            }
        ),
        model="fake-model",
        duration_ms=12,
    )
    event_service.extract(chapter.id, GenerationSettings(model="fake-model"))

    stored = event_repository.list_for_chapter(chapter.id)
    assert [event.summary for event in stored] == ["Mira leaves the archive."]


def test_extraction_rejects_empty_chapters(
    event_service: EventExtractionService, chapter_service, sample_project
) -> None:
    chapter = chapter_service.create_chapter(
        project_id=sample_project.id, title="Empty"
    )

    with pytest.raises(InvalidInputError, match="Add chapter text"):
        event_service.extract(
            chapter.id, GenerationSettings(model="fake-model")
        )


def test_deleting_a_chapter_removes_its_events(
    event_service: EventExtractionService,
    event_repository: EventRepository,
    chapter_service,
    fake_provider,
    sample_project,
) -> None:
    chapter = chapter_service.create_chapter(
        project_id=sample_project.id, title="The Gate", content="Mira enters."
    )
    fake_provider.result = GenerationResult(
        text=_payload(), model="fake-model", duration_ms=10
    )
    event_service.extract(chapter.id, GenerationSettings(model="fake-model"))
    assert event_repository.list_for_project(sample_project.id)

    chapter_service.delete_chapter(chapter.id)

    assert event_repository.list_for_project(sample_project.id) == []
