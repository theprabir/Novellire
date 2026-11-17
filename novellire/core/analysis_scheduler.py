"""Single-worker queue for automatic chapter analysis.

Saves enqueue a project; the worker analyses chapters sequentially. The queue is
in-process and daemon-backed, which is appropriate for a local single-user app.
Content hashes in ``analysis_state`` make repeated saves cheap and prevent
background work from running while Ollama is busy with interactive generation
because the provider itself is serialized.
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable

from ..logging_setup import get_logger
from ..storage.analysis_repository import AnalysisStateRepository
from .analysis import ChapterAnalysisService
from .settings_service import GenerationSettings
from .text import content_hash

logger = get_logger("core.analysis_scheduler")


class AnalysisScheduler:
    def __init__(
        self,
        analysis: ChapterAnalysisService,
        state_repository: AnalysisStateRepository,
        settings_provider: Callable[[], GenerationSettings],
        *,
        auto_run: bool,
    ) -> None:
        self._analysis = analysis
        self._state_repository = state_repository
        self._settings_provider = settings_provider
        self._auto_run = auto_run
        self._queue: queue.Queue[int | None] = queue.Queue()
        self._queued: set[int] = set()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not self._auto_run or self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._worker, name="novellire-analysis", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        if self._thread is None:
            return
        self._queue.put(None)
        self._thread.join(timeout=2)
        self._thread = None

    def schedule_chapter(self, chapter) -> None:  # noqa: ANN001 - chapter record
        if not chapter.content.strip():
            return
        digest = content_hash(chapter.content)
        current = self._state_repository.get(
            chapter.project_id, "chapter", str(chapter.id)
        )
        if (
            current is not None
            and current.content_hash == digest
            and current.status == "completed"
        ):
            return
        self._state_repository.mark(
            chapter.project_id,
            "chapter",
            str(chapter.id),
            digest,
            "pending",
        )
        self._enqueue(chapter.project_id)

    def schedule_document(self, project_id: int, kind: str, content: str) -> None:
        """Record the document hash and wake the chapter worker."""
        digest = content_hash(content)
        current = self._state_repository.get(project_id, "document", kind)
        if (
            current is not None
            and current.content_hash == digest
            and current.status == "completed"
        ):
            return
        self._state_repository.mark(
            project_id,
            "document",
            kind,
            digest,
            "completed",
            "Document saved; chapter memory will be checked.",
        )
        self._enqueue(project_id)

    def run_pending(self) -> None:
        """Process queued projects synchronously (tests and manual recovery)."""
        while True:
            try:
                project_id = self._queue.get_nowait()
            except queue.Empty:
                return
            if project_id is None:
                return
            with self._lock:
                self._queued.discard(project_id)
            self._process_project(project_id)

    def _enqueue(self, project_id: int) -> None:
        with self._lock:
            if project_id in self._queued:
                return
            self._queued.add(project_id)
        self._queue.put(project_id)

    def _worker(self) -> None:
        while True:
            project_id = self._queue.get()
            if project_id is None:
                return
            with self._lock:
                self._queued.discard(project_id)
            self._process_project(project_id)

    def _process_project(self, project_id: int) -> None:
        try:
            settings = self._settings_provider()
            for step in self._analysis.analyze_project(project_id, settings):
                if step.status == "failed":
                    logger.warning(
                        "Automatic analysis stopped: project=%s chapter=%s detail=%s",
                        project_id,
                        step.chapter_id,
                        step.detail,
                    )
                    return
        except Exception:  # noqa: BLE001 - background work must not kill the app
            logger.exception("Automatic analysis failed for project %s", project_id)
