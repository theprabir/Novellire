"""Bounded chapter drafting: one inference per scene beat, in order.

The server owns the loop. The model is asked for one scene at a time and never
chooses what runs next, so a plan of N beats costs N sequential inferences and
nothing else. The assembled draft is returned to the author; the chapter itself
is not changed until the text is inserted through the normal edit path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..errors import InvalidInputError, LLMResponseError
from ..storage.story_repositories import ChapterRecord
from .context import GenerationContextBuilder
from .generation import GenerationService
from .settings_service import GenerationSettings
from .text import count_words

MAX_SEQUENCE_SCENES = 6
MIN_SCENE_WORDS = 120
PREVIOUS_SCENE_CHARS = 800

_NUMBERED = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:scene\s+)?\d+[.):\-]\s+(.+)$", re.IGNORECASE
)
_BULLETED = re.compile(r"^\s*[-*\u2022\u2013]\s+(.+)$")


@dataclass(frozen=True)
class SceneDraft:
    index: int
    beat: str
    text: str
    model: str

    @property
    def word_count(self) -> int:
        return count_words(self.text)


@dataclass(frozen=True)
class SequenceDraft:
    scenes: tuple[SceneDraft, ...]
    text: str
    word_count: int
    model: str


def scene_beats(plan: str) -> list[str]:
    """Split a saved scene plan into beats.

    A numbered or bulleted line starts a beat and its following lines join it.
    A plan without markers treats each non-empty line as one beat.
    """
    beats: list[str] = []
    current = ""
    for raw in (plan or "").splitlines():
        line = raw.strip()
        if not line:
            # A blank line ends a beat, which keeps unmarked plans legible.
            if current:
                beats.append(current)
                current = ""
            continue
        match = _NUMBERED.match(line) or _BULLETED.match(line)
        if match is not None:
            if current:
                beats.append(current)
            current = match.group(1).strip()
        elif current:
            current = f"{current} {line}"
        else:
            current = line
    if current:
        beats.append(current)
    return beats


class ChapterDraftSequence:
    """Draft a chapter scene by scene from its saved scene plan."""

    def __init__(
        self,
        generation: GenerationService,
        context_builder: GenerationContextBuilder,
    ) -> None:
        self._generation = generation
        self._context_builder = context_builder

    def draft(
        self,
        *,
        project_id: int,
        chapter: ChapterRecord,
        settings: GenerationSettings,
        target_words: int,
        instructions: str = "",
    ) -> SequenceDraft:
        if chapter.status == "approved":
            raise InvalidInputError(
                "This chapter is approved. Reopen it before drafting into it."
            )
        plan = (chapter.objectives or "").strip()
        if not plan:
            raise InvalidInputError(
                "Add a scene plan to this chapter, or use Plan with AI first, "
                "so there are beats to draft."
            )
        beats = scene_beats(plan)
        if not beats:
            raise InvalidInputError("The scene plan has no beats to draft.")
        if len(beats) > MAX_SEQUENCE_SCENES:
            raise InvalidInputError(
                f"This plan has {len(beats)} scenes, more than one run drafts "
                f"({MAX_SEQUENCE_SCENES}). Merge beats into {MAX_SEQUENCE_SCENES} "
                "or draft a shorter plan."
            )

        total = len(beats)
        per_scene = max(MIN_SCENE_WORDS, int(target_words) // total)
        author_note = (instructions or "").strip()
        drafted: list[SceneDraft] = []
        previous = ""
        for index, beat in enumerate(beats, start=1):
            scene_title = f"Scene {index}"
            prompt = f"Scene {index} of {total}. {beat}"
            if author_note:
                prompt += f"\n\nAuthor instruction: {author_note}"
            if previous:
                prompt += (
                    "\n\nContinue from the end of the previous scene:\n"
                    f"{previous[-PREVIOUS_SCENE_CHARS:]}"
                )
            context = self._context_builder.build(
                project_id,
                instructions=prompt,
                chapter_id=chapter.id,
                chapter_title=chapter.title,
                scene_title=scene_title,
                context_notes=chapter.objectives,
                context_window=settings.context_window,
                output_tokens=settings.num_predict,
            )
            outcome = self._generation.generate(
                project_id=project_id,
                instructions=prompt,
                settings=settings,
                chapter_title=chapter.title,
                scene_title=scene_title,
                target_words=per_scene,
                context=context,
            )
            text = (outcome.text or "").strip()
            if not text:
                raise LLMResponseError(
                    f"The model returned an empty scene at beat {index}. "
                    "Try again or draft that beat in Chat."
                )
            drafted.append(
                SceneDraft(
                    index=index,
                    beat=beat,
                    text=text,
                    model=outcome.record.model or settings.model,
                )
            )
            previous = text

        assembled = "\n\n".join(scene.text for scene in drafted)
        return SequenceDraft(
            scenes=tuple(drafted),
            text=assembled,
            word_count=count_words(assembled),
            model=drafted[-1].model,
        )
