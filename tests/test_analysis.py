"""Automatic analysis of written chapters before a Chapter Map starts."""

from __future__ import annotations

import json

from novellire.core.analysis import ChapterAnalysisService
from novellire.core.events import EventExtractionService
from novellire.core.summaries import ChapterSummaryService
from novellire.llm.base import GenerationRequest, GenerationResult, ModelInfo
from novellire.storage.event_repository import EventDraft, EventRepository
from novellire.storage.story_repositories import CharacterRepository


class ScriptedProvider:
    def __init__(self, texts: list[str]) -> None:
        self.texts = texts
        self.requests: list[GenerationRequest] = []

    def is_available(self) -> bool:
        return True

    def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(name="fake-model")]

    def generate(self, request: GenerationRequest) -> GenerationResult:
        self.requests.append(request)
        text = self.texts.pop(0)
        return GenerationResult(text=text, model=request.model, duration_ms=5)


def _service(provider, database, project_repository, chapter_service):
    events = EventRepository(database)
    return ChapterAnalysisService(
        ChapterSummaryService(provider, project_repository, chapter_service),
        EventExtractionService(
            provider,
            project_repository,
            chapter_service,
            events,
            CharacterRepository(database),
        ),
        chapter_service,
        events,
    )


def test_analysis_fills_missing_memory_and_preserves_manual_records(
    database,
    project_repository,
    chapter_service,
    sample_project,
    generation_settings,
) -> None:
    first = chapter_service.create_chapter(
        project_id=sample_project.id,
        title="First",
        content="Mira arrives at the archive.",
    )
    second = chapter_service.create_chapter(
        project_id=sample_project.id,
        title="Second",
        content="Orin follows her.",
        summary="Author-written summary.",
    )
    third = chapter_service.create_chapter(
        project_id=sample_project.id,
        title="Third",
        content="The gate opens.",
        summary="Third summary.",
    )
    event_repository = EventRepository(database)
    event_repository.replace_for_chapter(
        sample_project.id,
        third.id,
        [EventDraft(summary="The gate opens.")],
        model="author",
    )

    provider = ScriptedProvider(
        [
            "Mira reaches the archive.",
            json.dumps(
                {
                    "events": [
                        {
                            "summary": "Mira arrives.",
                            "characters": ["Mira"],
                            "locations": ["Archive"],
                            "objects": [],
                            "threads": [],
                        }
                    ]
                }
            ),
            json.dumps(
                {
                    "events": [
                        {
                            "summary": "Orin follows.",
                            "characters": ["Orin"],
                            "locations": [],
                            "objects": [],
                            "threads": [],
                        }
                    ]
                }
            ),
        ]
    )
    service = _service(provider, database, project_repository, chapter_service)

    steps = list(
        service.analyze_before_position(
            sample_project.id, 4, generation_settings
        )
    )

    assert [step.status for step in steps] == [
        "analysed",
        "analysed",
        "skipped",
    ]
    assert len(provider.requests) == 3
    updated_first = chapter_service.require_chapter(first.id)
    updated_second = chapter_service.require_chapter(second.id)
    assert updated_first.summary == "Mira reaches the archive."
    assert updated_second.summary == "Author-written summary."
    assert len(event_repository.list_for_chapter(first.id)) == 1
    assert len(event_repository.list_for_chapter(second.id)) == 1
    assert len(event_repository.list_for_chapter(third.id)) == 1
    assert event_repository.list_for_chapter(third.id)[0].model == "author"