"""Pre-draft discussion: what the plan still leaves undecided.

One inference compares a saved scene plan with the chapter summary, documents,
canon, and retrieved memory, and asks a bounded set of questions whose answers
would change the prose. The answers are returned to the author; the plan itself
is never rewritten, and nothing is drafted until the author asks for it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from ..errors import InvalidInputError, LLMResponseError, ProjectNotFoundError
from ..llm.base import GenerationRequest, LLMProvider
from ..prompts.templates import build_plan_discussion_prompt
from ..storage.repositories import ProjectRepository
from .chapters import ChapterService
from .context import GenerationContextBuilder, prompt_blocks
from .settings_service import GenerationSettings

DISCUSS_PLAN_CHARS = 6_000
DISCUSS_MAX_QUESTIONS = 5
DISCUSS_MAX_OUTPUT_TOKENS = 800
DISCUSS_QUESTION_CHARS = 300
DISCUSS_WHY_CHARS = 300
DISCUSS_SUMMARY_CHARS = 600


@dataclass(frozen=True)
class PlanQuestion:
    id: int
    question: str
    why: str


@dataclass(frozen=True)
class PlanDiscussion:
    ready: bool
    summary: str
    questions: tuple[PlanQuestion, ...]
    model: str


class ChapterDiscussionService:
    """Ask what the plan still needs before prose is drafted."""

    def __init__(
        self,
        provider: LLMProvider,
        projects: ProjectRepository,
        chapters: ChapterService,
        context_builder: GenerationContextBuilder,
    ) -> None:
        self._provider = provider
        self._projects = projects
        self._chapters = chapters
        self._context_builder = context_builder

    def discuss(
        self, chapter_id: int, *, settings: GenerationSettings
    ) -> PlanDiscussion:
        chapter = self._chapters.require_chapter(chapter_id)
        project = self._projects.get(chapter.project_id)
        if project is None:
            raise ProjectNotFoundError(
                "That project no longer exists. Choose another project."
            )
        plan = (chapter.objectives or "").strip()
        if not plan:
            raise InvalidInputError(
                "Add a scene plan to this chapter, or use Plan with AI first, "
                "before discussing it."
            )
        if len(plan) > DISCUSS_PLAN_CHARS:
            raise InvalidInputError(
                f"This scene plan is {len(plan):,} characters, more than one "
                f"discussion can carry ({DISCUSS_PLAN_CHARS:,}). Tighten the "
                "plan first, so no part of it is dropped."
            )
        model = (settings.model or "").strip()
        if not model:
            raise InvalidInputError("Choose a model before discussing a plan.")

        context = self._context_builder.build(
            project.id,
            instructions=plan,
            chapter_id=chapter.id,
            chapter_title=chapter.title,
            context_notes=chapter.summary or plan,
            context_window=settings.context_window,
            output_tokens=min(settings.num_predict, DISCUSS_MAX_OUTPUT_TOKENS),
        )
        system_prompt, user_prompt = build_plan_discussion_prompt(
            project_name=project.name,
            genre=project.genre,
            narrative_style=project.narrative_style,
            plan=context.chapter_plan or plan,
            chapter_title=chapter.title,
            chapter_position=chapter.position,
            chapter_summary=chapter.summary,
            **prompt_blocks(context),
        )
        result = self._provider.generate(
            GenerationRequest(
                prompt=user_prompt,
                system_prompt=system_prompt,
                model=model,
                temperature=0.3,
                top_p=settings.top_p,
                num_predict=min(
                    max(settings.num_predict, 400), DISCUSS_MAX_OUTPUT_TOKENS
                ),
                context_window=settings.context_window,
            )
        )
        ready, summary, questions = parse_discussion_payload(result.text)
        return PlanDiscussion(
            ready=ready,
            summary=summary,
            questions=tuple(questions),
            model=result.model or model,
        )


def parse_discussion_payload(
    text: str,
) -> tuple[bool, str, list[PlanQuestion]]:
    """Parse the discussion JSON, keeping questions that add something new."""
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise LLMResponseError(
            "The model did not return a plan-discussion JSON object."
        )
    try:
        data = json.loads(text[start : end + 1])
    except (TypeError, ValueError) as exc:
        raise LLMResponseError(
            "The model returned invalid plan-discussion JSON."
        ) from exc
    if not isinstance(data, dict):
        raise LLMResponseError(
            "The model returned an unexpected plan-discussion structure."
        )

    raw_ready = data.get("ready")
    ready = raw_ready is True or (
        isinstance(raw_ready, str) and raw_ready.strip().casefold() == "true"
    )
    summary = _phrase(data.get("summary"), DISCUSS_SUMMARY_CHARS)
    questions: list[PlanQuestion] = []
    seen: set[str] = set()
    items = data.get("questions")
    for item in items if isinstance(items, list) else []:
        if isinstance(item, str):
            question, why = _phrase(item, DISCUSS_QUESTION_CHARS), ""
        elif isinstance(item, dict):
            question = _phrase(item.get("question"), DISCUSS_QUESTION_CHARS)
            why = _phrase(item.get("why"), DISCUSS_WHY_CHARS)
        else:
            continue
        if not question:
            continue
        key = question.casefold()
        if key in seen:
            continue
        seen.add(key)
        questions.append(
            PlanQuestion(id=len(questions) + 1, question=question, why=why)
        )
        if len(questions) >= DISCUSS_MAX_QUESTIONS:
            break
    return ready, summary, questions


def _phrase(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit].strip()
