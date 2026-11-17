"""Analysis across every written chapter, hashes, and derived insights."""

from __future__ import annotations

import json

from novellire.core.analysis import ChapterAnalysisService
from novellire.core.analysis_scheduler import AnalysisScheduler
from novellire.core.events import EventExtractionService
from novellire.core.insights import ChapterInsightService
from novellire.core.summaries import ChapterSummaryService
from novellire.llm.base import GenerationRequest, GenerationResult, ModelInfo
from novellire.storage.analysis_repository import (
    AnalysisStateRepository,
    ChapterInsightRepository,
)
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


def _insights_payload(name: str) -> str:
    return json.dumps(
        {
            "character_states": [
                {
                    "name": name,
                    "location": "Archive",
                    "status": "watching",
                    "goals": "Learn the truth",
                    "knowledge": "The gate exists",
                }
            ],
            "locations": [
                {"name": "Archive", "description": "A buried record room."}
            ],
            "relationships": [
                {
                    "character_a": name,
                    "character_b": "Orin",
                    "relation_type": "ally",
                    "description": "They share a secret.",
                }
            ],
            "open_threads": ["Who opened the gate?"],
        }
    )


def _service(provider, database, project_repository, chapter_service):
    events = EventRepository(database)
    insights = ChapterInsightRepository(database)
    state = AnalysisStateRepository(database)
    insight_service = ChapterInsightService(
        provider,
        project_repository,
        chapter_service,
        CharacterRepository(database),
        insights,
    )
    analysis = ChapterAnalysisService(
        ChapterSummaryService(provider, project_repository, chapter_service),
        EventExtractionService(
            provider,
            project_repository,
            chapter_service,
            events,
            CharacterRepository(database),
        ),
        insight_service,
        chapter_service,
        events,
        insights,
        state,
    )
    return analysis, insight_service, insights, state


def test_analysis_fills_every_written_chapter_and_preserves_manual_records(
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
            _insights_payload("Mira"),
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
            _insights_payload("Orin"),
            _insights_payload("Mira"),
        ]
    )
    service, _, insights, state = _service(
        provider, database, project_repository, chapter_service
    )

    steps = list(service.analyze_project(sample_project.id, generation_settings))

    assert [step.status for step in steps] == [
        "analysed",
        "analysed",
        "analysed",
    ], [(step.status, step.detail) for step in steps]
    assert len(provider.requests) == 6
    updated_first = chapter_service.require_chapter(first.id)
    updated_second = chapter_service.require_chapter(second.id)
    assert updated_first.summary == "Mira reaches the archive."
    assert updated_second.summary == "Author-written summary."
    assert len(event_repository.list_for_chapter(first.id)) == 1
    assert len(event_repository.list_for_chapter(second.id)) == 1
    assert len(event_repository.list_for_chapter(third.id)) == 1
    assert event_repository.list_for_chapter(third.id)[0].model == "author"
    assert insights.get_for_chapter(third.id).open_threads == (
        "Who opened the gate?",
    )
    assert state.get(sample_project.id, "chapter", str(first.id)).status == (
        "completed"
    )

    again = list(service.analyze_project(sample_project.id, generation_settings))
    assert [step.status for step in again] == ["skipped", "skipped", "skipped"]
    assert len(provider.requests) == 6

    chapter_service.update_chapter(first.id, content="Mira leaves the archive.")
    provider.texts.append(_insights_payload("Mira"))
    refreshed = list(
        service.analyze_project(sample_project.id, generation_settings)
    )
    assert refreshed[0].status == "analysed"
    assert refreshed[0].detail == "Added insights."
    assert len(provider.requests) == 7


def test_scheduler_records_document_hashes_and_queues_changed_chapters(
    database,
    project_repository,
    chapter_service,
    sample_project,
    generation_settings,
) -> None:
    chapter = chapter_service.create_chapter(
        project_id=sample_project.id,
        title="First",
        content="Mira arrives at the archive.",
    )
    provider = ScriptedProvider(
        [
            "Mira reaches the archive.",
            json.dumps({"events": []}),
            _insights_payload("Mira"),
        ]
    )
    analysis, _, _, state = _service(
        provider, database, project_repository, chapter_service
    )
    scheduler = AnalysisScheduler(
        analysis,
        state,
        lambda: generation_settings,
        auto_run=False,
    )

    scheduler.schedule_chapter(chapter)
    scheduler.run_pending()

    assert len(provider.requests) == 3
    assert state.get(sample_project.id, "chapter", str(chapter.id)).status == (
        "completed"
    )

    scheduler.schedule_chapter(chapter)
    scheduler.run_pending()
    assert len(provider.requests) == 3

    scheduler.schedule_document(
        sample_project.id, "character_bible", "Mira has a scar."
    )
    scheduler.run_pending()
    assert len(provider.requests) == 3
    document_state = state.get(
        sample_project.id, "document", "character_bible"
    )
    assert document_state.status == "completed"
    assert document_state.content_hash
