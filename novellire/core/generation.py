"""Generation service: the single path from author request to saved prose."""

from __future__ import annotations

import time
from dataclasses import dataclass

from ..errors import InvalidInputError, LLMError, ProjectNotFoundError
from ..llm.base import GenerationRequest, LLMProvider
from ..logging_setup import get_logger
from ..prompts.templates import build_planning_prompt, build_writing_prompt
from ..storage.repositories import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    GenerationRecord,
    GenerationRepository,
    ProjectRepository,
)
from .context import GenerationContext
from .settings_service import GenerationSettings
from .text import count_words

logger = get_logger("core.generation")

DEFAULT_TARGET_WORDS = 900
MIN_TARGET_WORDS = 50
MAX_TARGET_WORDS = 6000


@dataclass(frozen=True)
class GenerationOutcome:
    """A saved generation, successful or not, plus its persisted record."""

    record: GenerationRecord

    @property
    def text(self) -> str:
        return self.record.output

    @property
    def word_count(self) -> int:
        return self.record.word_count


class GenerationService:
    """Builds prompts, calls the provider once, and records the attempt."""

    def __init__(
        self,
        provider: LLMProvider,
        projects: ProjectRepository,
        generations: GenerationRepository,
        *,
        default_target_words: int = DEFAULT_TARGET_WORDS,
    ) -> None:
        self._provider = provider
        self._projects = projects
        self._generations = generations
        self._default_target_words = default_target_words

    def generate(
        self,
        *,
        project_id: int,
        instructions: str,
        settings: GenerationSettings,
        chapter_title: str = "",
        scene_title: str = "",
        context_notes: str = "",
        target_words: int | None = None,
        context: GenerationContext | None = None,
    ) -> GenerationOutcome:
        project = self._projects.get(project_id)
        if project is None:
            raise ProjectNotFoundError(
                "That project no longer exists. Choose another project."
            )

        cleaned_instructions = (instructions or "").strip()
        if not cleaned_instructions:
            raise InvalidInputError(
                "Describe what should happen in the scene before generating."
            )

        model = (settings.model or "").strip()
        if not model:
            raise InvalidInputError(
                "Choose a model before generating. Install one with "
                "`ollama pull qwen2.5:1.5b` if the list is empty."
            )

        target = self._default_target_words if target_words is None else int(target_words)
        if target < MIN_TARGET_WORDS or target > MAX_TARGET_WORDS:
            raise InvalidInputError(
                f"Target length must be between {MIN_TARGET_WORDS} and "
                f"{MAX_TARGET_WORDS} words for a single scene."
            )

        narrative = context or GenerationContext()
        system_prompt, user_prompt = build_writing_prompt(
            project_name=project.name,
            genre=project.genre,
            narrative_style=project.narrative_style,
            instructions=cleaned_instructions,
            target_words=target,
            chapter_title=(chapter_title or "").strip(),
            chapter_plan=_clip(
                narrative.chapter_plan, narrative.budget.chapter_plan_chars
            ),
            scene_title=(scene_title or "").strip(),
            context_notes=(context_notes or "").strip(),
            master_bible=_clip(
                narrative.master_bible, narrative.budget.master_bible_chars
            ),
            character_bible=_clip(
                narrative.character_bible, narrative.budget.character_bible_chars
            ),
            chapter_map=_clip(
                narrative.chapter_map, narrative.budget.chapter_map_chars
            ),
            style_guide=_clip(
                narrative.style_guide, narrative.budget.style_guide_chars
            ),
            earlier_chapters=narrative.earlier_chapters,
            earlier_events=narrative.earlier_events,
            bible_entries=narrative.bible_entries,
            character_profiles=narrative.character_profiles,
            relationship_records=narrative.relationship_records,
            character_states=narrative.character_states,
        )

        return self._complete(
            project_id, system_prompt, user_prompt, model, settings
        )

    def generate_plan(
        self,
        *,
        project_id: int,
        instructions: str,
        settings: GenerationSettings,
        chapter_title: str = "",
        chapter_summary: str = "",
        chapter_plan: str = "",
        context: GenerationContext | None = None,
    ) -> GenerationOutcome:
        """Generate an editable scene plan, without changing chapter text."""
        project = self._projects.get(project_id)
        if project is None:
            raise ProjectNotFoundError(
                "That project no longer exists. Choose another project."
            )
        model = (settings.model or "").strip()
        if not model:
            raise InvalidInputError(
                "Choose a model before planning. Install one with "
                "`ollama pull qwen2.5:1.5b` if the list is empty."
            )

        narrative = context or GenerationContext()
        system_prompt, user_prompt = build_planning_prompt(
            project_name=project.name,
            genre=project.genre,
            narrative_style=project.narrative_style,
            instructions=(instructions or "").strip(),
            chapter_title=(chapter_title or "").strip(),
            chapter_summary=(chapter_summary or "").strip(),
            existing_plan=(chapter_plan or "").strip(),
            master_bible=_clip(
                narrative.master_bible, narrative.budget.master_bible_chars
            ),
            character_bible=_clip(
                narrative.character_bible, narrative.budget.character_bible_chars
            ),
            chapter_map=_clip(
                narrative.chapter_map, narrative.budget.chapter_map_chars
            ),
            style_guide=_clip(
                narrative.style_guide, narrative.budget.style_guide_chars
            ),
            earlier_chapters=narrative.earlier_chapters,
            earlier_events=narrative.earlier_events,
            bible_entries=narrative.bible_entries,
            character_profiles=narrative.character_profiles,
            relationship_records=narrative.relationship_records,
            character_states=narrative.character_states,
        )
        return self._complete(
            project_id, system_prompt, user_prompt, model, settings
        )

    def _complete(
        self,
        project_id: int,
        system_prompt: str,
        user_prompt: str,
        model: str,
        settings: GenerationSettings,
    ) -> GenerationOutcome:
        request = GenerationRequest(
            prompt=user_prompt,
            system_prompt=system_prompt,
            model=model,
            temperature=settings.temperature,
            top_p=settings.top_p,
            num_predict=settings.num_predict,
            context_window=settings.context_window,
        )

        started = time.perf_counter()
        try:
            result = self._provider.generate(request)
        except LLMError as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            self._record_failure(
                project_id=project_id,
                request=request,
                error=str(exc),
                duration_ms=elapsed_ms,
            )
            raise

        record = self._generations.create(
            project_id=project_id,
            model=result.model or model,
            system_prompt=system_prompt,
            prompt=user_prompt,
            output=result.text,
            word_count=count_words(result.text),
            temperature=settings.temperature,
            top_p=settings.top_p,
            num_predict=settings.num_predict,
            context_window=settings.context_window,
            status=STATUS_COMPLETED,
            duration_ms=result.duration_ms,
            prompt_tokens=result.prompt_tokens,
            output_tokens=result.output_tokens,
            truncated=result.truncated,
        )
        logger.info(
            "Saved generation id=%s project=%s model=%s words=%s duration_ms=%s",
            record.id,
            project_id,
            record.model,
            record.word_count,
            record.duration_ms,
        )
        return GenerationOutcome(record=record)

    def _record_failure(
        self,
        *,
        project_id: int,
        request: GenerationRequest,
        error: str,
        duration_ms: int,
    ) -> None:
        """Persist a failed attempt without masking the original error."""
        try:
            self._generations.create(
                project_id=project_id,
                model=request.model,
                system_prompt=request.system_prompt,
                prompt=request.prompt,
                status=STATUS_FAILED,
                error=error[:2000],
                temperature=request.temperature,
                top_p=request.top_p,
                num_predict=request.num_predict,
                context_window=request.context_window,
                duration_ms=duration_ms,
            )
        except Exception:  # noqa: BLE001 - never hide the inference failure
            logger.exception("Could not record a failed generation attempt")
        logger.warning(
            "Generation failed: project=%s model=%s duration_ms=%s",
            project_id,
            request.model,
            duration_ms,
        )


def _clip(text: str, limit: int) -> str:
    """Keep one prompt block inside its share of the context budget."""
    return (text or "")[:limit]
