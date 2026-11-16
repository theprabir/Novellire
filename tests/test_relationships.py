"""Typed, author-approved relationship records."""

from __future__ import annotations

import pytest

from novellire.core.relationships import RelationshipService
from novellire.errors import InvalidInputError, RecordNotFoundError
from novellire.storage.event_repository import EventDraft, EventRepository
from novellire.storage.relationship_repository import RelationshipRepository
from novellire.storage.story_repositories import CharacterRepository


@pytest.fixture()
def relationship_service(
    database, project_repository
) -> RelationshipService:
    return RelationshipService(
        project_repository,
        CharacterRepository(database),
        EventRepository(database),
        RelationshipRepository(database),
    )


def test_creates_a_proposed_record_in_canonical_order(
    relationship_service: RelationshipService,
    character_service,
    sample_project,
) -> None:
    mira = character_service.create_character(
        project_id=sample_project.id, name="Mira Voss"
    )
    orin = character_service.create_character(
        project_id=sample_project.id, name="Orin Vale"
    )

    record = relationship_service.create(
        sample_project.id,
        character_a_id=orin.id,
        character_b_id=mira.id,
        relation_type="ally",
        description="They guard the archive together.",
    )

    assert record.character_a_id == mira.id
    assert record.character_b_id == orin.id
    assert record.character_a_name == "Mira Voss"
    assert record.character_b_name == "Orin Vale"
    assert record.relation_type == "ally"
    assert record.status == "proposed"
    assert record.source_event_id is None
    assert relationship_service.list_for_project(sample_project.id) == [record]


def test_status_actions_control_canon(
    relationship_service: RelationshipService,
    character_service,
    sample_project,
) -> None:
    mira = character_service.create_character(
        project_id=sample_project.id, name="Mira Voss"
    )
    orin = character_service.create_character(
        project_id=sample_project.id, name="Orin Vale"
    )
    record = relationship_service.create(
        sample_project.id,
        character_a_id=mira.id,
        character_b_id=orin.id,
        relation_type="rival",
    )

    approved = relationship_service.set_status(record.id, "approved")
    assert approved.status == "approved"
    rejected = relationship_service.set_status(record.id, "rejected")
    assert rejected.status == "rejected"
    reopened = relationship_service.set_status(record.id, "proposed")
    assert reopened.status == "proposed"

    with pytest.raises(InvalidInputError, match="valid relationship status"):
        relationship_service.set_status(record.id, "canon")


def test_updates_type_and_description(
    relationship_service: RelationshipService,
    character_service,
    sample_project,
) -> None:
    mira = character_service.create_character(
        project_id=sample_project.id, name="Mira Voss"
    )
    orin = character_service.create_character(
        project_id=sample_project.id, name="Orin Vale"
    )
    record = relationship_service.create(
        sample_project.id,
        character_a_id=mira.id,
        character_b_id=orin.id,
        relation_type="ally",
    )

    updated = relationship_service.update(
        record.id,
        relation_type="family",
        description="Siblings by choice, not blood.",
    )

    assert updated.relation_type == "family"
    assert updated.description == "Siblings by choice, not blood."

    with pytest.raises(InvalidInputError, match="valid relationship type"):
        relationship_service.update(record.id, relation_type="nemesis")


def test_rejects_invalid_pairs_and_projects(
    relationship_service: RelationshipService,
    character_service,
    project_service,
    sample_project,
) -> None:
    mira = character_service.create_character(
        project_id=sample_project.id, name="Mira Voss"
    )
    keeper = character_service.create_character(
        project_id=sample_project.id, name="The Keeper"
    )
    other = project_service.create_project(name="Elsewhere")
    outsider = character_service.create_character(
        project_id=other.id, name="Orin Vale"
    )

    with pytest.raises(InvalidInputError, match="two different characters"):
        relationship_service.create(
            sample_project.id,
            character_a_id=mira.id,
            character_b_id=mira.id,
            relation_type="ally",
        )
    with pytest.raises(InvalidInputError, match="characters from this project"):
        relationship_service.create(
            sample_project.id,
            character_a_id=mira.id,
            character_b_id=outsider.id,
            relation_type="ally",
        )
    with pytest.raises(InvalidInputError, match="valid relationship type"):
        relationship_service.create(
            sample_project.id,
            character_a_id=mira.id,
            character_b_id=keeper.id,
            relation_type="nemesis",
        )


def test_records_source_event_provenance(
    relationship_service: RelationshipService,
    character_service,
    chapter_service,
    database,
    sample_project,
) -> None:
    mira = character_service.create_character(
        project_id=sample_project.id, name="Mira Voss"
    )
    orin = character_service.create_character(
        project_id=sample_project.id, name="Orin Vale"
    )
    chapter = chapter_service.create_chapter(
        project_id=sample_project.id, title="The Gate", content="They meet."
    )
    events = EventRepository(database)
    events.replace_for_chapter(
        sample_project.id,
        chapter.id,
        [
            EventDraft(
                summary="Mira and Orin open the gate.",
                characters=("Mira", "Orin"),
            )
        ],
        model="fake-model",
    )
    event = events.list_for_chapter(chapter.id)[0]

    record = relationship_service.create(
        sample_project.id,
        character_a_id=mira.id,
        character_b_id=orin.id,
        relation_type="ally",
        source_event_id=event.id,
    )

    assert record.source_event_id == event.id
    assert record.source_chapter_title == "The Gate"
    assert record.source_chapter_position == 1
    assert record.source_summary == "Mira and Orin open the gate."


def test_deletes_a_record(
    relationship_service: RelationshipService,
    character_service,
    sample_project,
) -> None:
    mira = character_service.create_character(
        project_id=sample_project.id, name="Mira Voss"
    )
    orin = character_service.create_character(
        project_id=sample_project.id, name="Orin Vale"
    )
    record = relationship_service.create(
        sample_project.id,
        character_a_id=mira.id,
        character_b_id=orin.id,
        relation_type="debt",
    )

    relationship_service.delete(record.id)

    assert relationship_service.list_for_project(sample_project.id) == []
    with pytest.raises(RecordNotFoundError):
        relationship_service.delete(record.id)
