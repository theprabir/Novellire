"""Context-window budgeting for documents and retrieved memory."""

from __future__ import annotations

from novellire.core.context import (
    CHARS_PER_TOKEN,
    CONTEXT_RESERVE_TOKENS,
    ContextBudget,
    GenerationContext,
    MemoryChapter,
)
from novellire.core.generation import GenerationService
from novellire.core.settings_service import GenerationSettings
from novellire.storage.repositories import Project


def test_larger_window_allocates_more_prompt_space() -> None:
    small = ContextBudget.from_window(4096, 700)
    large = ContextBudget.from_window(16384, 700)

    assert large.total_chars > small.total_chars * 3
    assert large.master_bible_chars > small.master_bible_chars
    assert large.memory_chars > small.memory_chars
    assert large.total_chars == (
        16384 - 700 - CONTEXT_RESERVE_TOKENS
    ) * CHARS_PER_TOKEN


def test_retrieved_memory_expands_with_the_window() -> None:
    chapters = tuple(
        MemoryChapter(
            id=index,
            position=index,
            title=f"Chapter {index}",
            summary="summary " * 80,
            excerpt="passage " * 120,
        )
        for index in range(1, 7)
    )
    small = GenerationContext(
        memory_chapters=chapters,
        budget=ContextBudget.from_window(4096, 700),
    )
    large = GenerationContext(
        memory_chapters=chapters,
        budget=ContextBudget.from_window(16384, 700),
    )

    assert len(large.earlier_chapters) > len(small.earlier_chapters)


def test_generation_prompt_uses_the_larger_document_budget(
    generation_service: GenerationService,
    fake_provider,
    sample_project: Project,
    generation_settings: GenerationSettings,
) -> None:
    text = "Alpha " * 10_000

    generation_service.generate(
        project_id=sample_project.id,
        instructions="Continue.",
        settings=generation_settings,
        context=GenerationContext(
            master_bible=text,
            budget=ContextBudget.from_window(4096, 700),
        ),
    )
    small_prompt = fake_provider.requests[-1].prompt

    generation_service.generate(
        project_id=sample_project.id,
        instructions="Continue.",
        settings=generation_settings,
        context=GenerationContext(
            master_bible=text,
            budget=ContextBudget.from_window(16384, 700),
        ),
    )
    large_prompt = fake_provider.requests[-1].prompt

    assert large_prompt.count("Alpha") > small_prompt.count("Alpha")