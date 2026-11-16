"""Generation service tests: prompt construction, persistence, and failures."""

from __future__ import annotations

import pytest

from novellire.core.context import GenerationContext
from novellire.core.generation import GenerationService, count_words
from novellire.core.settings_service import GenerationSettings
from novellire.errors import (
    DatabaseError,
    InvalidInputError,
    LLMUnavailableError,
    ProjectNotFoundError,
)
from novellire.llm.base import GenerationResult
from novellire.storage.repositories import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    Project,
    ProjectRepository,
)


def test_generate_saves_completed_record(
    generation_service: GenerationService,
    generation_repository,
    fake_provider,
    sample_project: Project,
    generation_settings: GenerationSettings,
) -> None:
    outcome = generation_service.generate(
        project_id=sample_project.id,
        instructions="Mira discovers the sealed vault.",
        settings=generation_settings,
        chapter_title="Chapter 1",
        scene_title="The Vault",
        target_words=300,
    )

    assert outcome.word_count == 120
    record = generation_repository.get(outcome.record.id)
    assert record is not None
    assert record.status == STATUS_COMPLETED
    assert record.project_id == sample_project.id
    assert record.model == "fake-model"
    assert record.output == outcome.text
    assert record.truncated is False
    assert record.prompt_tokens == 10
    assert record.output_tokens == 120


def test_generate_builds_prompt_from_project_and_instructions(
    generation_service: GenerationService,
    fake_provider: FakeProvider,
    sample_project: Project,
    generation_settings: GenerationSettings,
) -> None:
    generation_service.generate(
        project_id=sample_project.id,
        instructions="Mira discovers the sealed vault.",
        settings=generation_settings,
        chapter_title="Chapter 1",
        scene_title="The Vault",
        context_notes="The vault has no keyhole.",
        target_words=300,
    )

    request = fake_provider.requests[-1]
    assert "Ashfall" in request.system_prompt
    assert "Science fiction" in request.system_prompt
    assert "Mira discovers the sealed vault." in request.prompt
    assert "Chapter: Chapter 1" in request.prompt
    assert "Scene: The Vault" in request.prompt
    assert "The vault has no keyhole." in request.prompt
    assert "about 300 words" in request.prompt
    assert request.model == "fake-model"
    assert request.temperature == 0.7
    assert request.context_window == 2048


def test_prompt_includes_approved_relationship_records(
    generation_service: GenerationService,
    fake_provider,
    sample_project: Project,
    generation_settings: GenerationSettings,
) -> None:
    generation_service.generate(
        project_id=sample_project.id,
        instructions="Mira meets Orin.",
        settings=generation_settings,
        context=GenerationContext(
            relationship_records=(
                "Mira Voss — Orin Vale: Ally — They guard the archive."
            )
        ),
    )

    prompt = fake_provider.requests[-1].prompt
    assert "Approved character relationships:" in prompt
    assert "Mira Voss — Orin Vale: Ally" in prompt


def test_prompt_includes_current_character_state(
    generation_service: GenerationService,
    fake_provider,
    sample_project: Project,
    generation_settings: GenerationSettings,
) -> None:
    generation_service.generate(
        project_id=sample_project.id,
        instructions="Mira waits at the gate.",
        settings=generation_settings,
        context=GenerationContext(
            character_states=(
                "Mira Voss (as of Chapter 2 — Part Two)\n"
                "Location: The keep"
            )
        ),
    )

    prompt = fake_provider.requests[-1].prompt
    assert "Current character state:" in prompt
    assert "Mira Voss (as of Chapter 2 — Part Two)" in prompt


def test_generate_uses_default_target_when_omitted(
    generation_service: GenerationService,
    fake_provider,
    sample_project: Project,
    generation_settings: GenerationSettings,
) -> None:
    generation_service.generate(
        project_id=sample_project.id,
        instructions="A quiet argument.",
        settings=generation_settings,
    )
    assert "about 900 words" in fake_provider.requests[-1].prompt


def test_failed_generation_is_recorded_and_reraised(
    fake_provider_factory,
    project_repository: ProjectRepository,
    generation_repository,
    sample_project: Project,
    generation_settings: GenerationSettings,
) -> None:
    provider = fake_provider_factory(
        error=LLMUnavailableError("Ollama is not running.")
    )
    service = GenerationService(provider, project_repository, generation_repository)

    with pytest.raises(LLMUnavailableError, match="not running"):
        service.generate(
            project_id=sample_project.id,
            instructions="Mira waits.",
            settings=generation_settings,
        )

    records = generation_repository.list_for_project(sample_project.id)
    assert len(records) == 1
    assert records[0].status == STATUS_FAILED
    assert records[0].output == ""
    assert "not running" in (records[0].error or "")
    assert records[0].word_count == 0


def test_failure_recording_does_not_mask_provider_error(
    fake_provider_factory,
    project_repository: ProjectRepository,
    sample_project: Project,
) -> None:
    class BrokenGenerationRepository:
        def create(self, **_: object):
            raise DatabaseError("disk is full")

    service = GenerationService(
        fake_provider_factory(error=LLMUnavailableError("Ollama is not running.")),
        project_repository,
        BrokenGenerationRepository(),  # type: ignore[arg-type]
    )

    with pytest.raises(LLMUnavailableError):
        service.generate(
            project_id=sample_project.id,
            instructions="Mira waits.",
            settings=GenerationSettings(model="fake-model"),
        )


def test_empty_instructions_are_rejected(
    generation_service: GenerationService,
    generation_repository,
    sample_project: Project,
    generation_settings: GenerationSettings,
) -> None:
    with pytest.raises(InvalidInputError):
        generation_service.generate(
            project_id=sample_project.id,
            instructions="   ",
            settings=generation_settings,
        )
    assert generation_repository.count_for_project(sample_project.id) == 0


def test_missing_project_is_rejected(
    generation_service: GenerationService, generation_settings: GenerationSettings
) -> None:
    with pytest.raises(ProjectNotFoundError):
        generation_service.generate(
            project_id=4242, instructions="Anything.", settings=generation_settings
        )


def test_missing_model_is_rejected(
    generation_service: GenerationService,
    sample_project: Project,
) -> None:
    with pytest.raises(InvalidInputError, match="Choose a model"):
        generation_service.generate(
            project_id=sample_project.id,
            instructions="Anything.",
            settings=GenerationSettings(model=""),
        )


@pytest.mark.parametrize("target", [10, 9000])
def test_out_of_range_target_is_rejected(
    generation_service: GenerationService,
    sample_project: Project,
    generation_settings: GenerationSettings,
    target: int,
) -> None:
    with pytest.raises(InvalidInputError):
        generation_service.generate(
            project_id=sample_project.id,
            instructions="Anything.",
            settings=generation_settings,
            target_words=target,
        )


def test_truncated_result_is_propagated(
    fake_provider_factory,
    project_repository: ProjectRepository,
    generation_repository,
    sample_project: Project,
) -> None:
    provider = fake_provider_factory(
        result=GenerationResult(
            text="An unfinished sent", model="fake-model", duration_ms=5, truncated=True
        )
    )
    service = GenerationService(provider, project_repository, generation_repository)

    outcome = service.generate(
        project_id=sample_project.id,
        instructions="Cut off mid-sentence.",
        settings=GenerationSettings(model="fake-model"),
    )

    assert outcome.record.truncated is True
    assert outcome.word_count == 3


def test_saved_records_are_listed_newest_first(
    generation_service: GenerationService,
    generation_repository,
    sample_project: Project,
    generation_settings: GenerationSettings,
) -> None:
    for index in range(3):
        generation_service.generate(
            project_id=sample_project.id,
            instructions=f"Scene number {index}.",
            settings=generation_settings,
        )

    records = generation_repository.list_for_project(sample_project.id)
    assert len(records) == 3
    assert records[0].id > records[-1].id
    assert generation_repository.produced_words(sample_project.id) == 360


def test_count_words_handles_whitespace() -> None:
    assert count_words("  one   two\nthree ") == 3
    assert count_words("") == 0
