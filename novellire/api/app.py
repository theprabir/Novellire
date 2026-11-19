"""FastAPI application: JSON API plus the static browser client.

The API is a thin transport layer. Validation, prompt construction, storage, and
inference all live in the existing services, so the browser client and the CLI
share exactly the same rules.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.background import BackgroundTask
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import __version__
from ..config import Settings, load_settings
from ..core.analysis import ChapterAnalysisService
from ..core.analysis_scheduler import AnalysisScheduler
from ..core.backup import BackupService
from ..core.chapters import ChapterService
from ..core.character_states import CharacterStateService
from ..core.characters import FIELD_LABELS as CHARACTER_FIELD_LABELS
from ..core.characters import PROFILE_FIELDS, CharacterService
from ..core.chat import ChatService
from ..core.context import GenerationContextBuilder
from ..core.continuity import ContinuityCheckService, ContinuityLedgerService
from ..core.state_proposals import (
    CharacterStateProposalService,
    StateUpdateInput,
)
from ..core.threads import ThreadService
from ..core.discussion import ChapterDiscussionService
from ..core.documents import ProjectDocumentService, WORKSPACE_DOCUMENTS
from ..core.events import EventExtractionService
from ..core.export import ExportService
from ..core.generation import GenerationService
from ..core.insights import ChapterInsightService
from ..core.memory import MemoryService
from ..core.orchestration import ChapterDraftSequence
from ..core.review import ChapterReviewService
from ..core.outline import OutlineService
from ..core.projects import ProjectService
from ..core.relationships import (
    RELATIONSHIP_TYPE_LABELS,
    RelationshipService,
)
from ..core.scenes import SceneService
from ..core.settings_service import (
    ACCENTS,
    READING_FONTS,
    READING_WIDTHS,
    THEMES,
    UI_FONTS,
    AppearanceSettings,
    AppSettingsService,
    GenerationSettings,
)
from ..core.story_bible import (
    STORY_BIBLE_CATEGORIES,
    StoryBibleService,
)
from ..core.style_guide import StyleGuideService
from ..core.summaries import ChapterSummaryService
from ..core.work_status import WORK_STATUSES, WORK_STATUS_LABELS
from ..errors import (
    DuplicateEntryError,
    DuplicateProjectError,
    InvalidInputError,
    LLMError,
    NovellireError,
    ProjectNotFoundError,
    RecordNotFoundError,
)
from ..llm.base import LLMProvider
from ..llm.ollama import OllamaProvider
from ..llm.serialized import SerializedProvider
from ..logging_setup import configure_logging
from ..storage.database import Database
from ..storage.analysis_repository import (
    AnalysisStateRepository,
    ChapterInsightRepository,
)
from ..storage.chat_repository import ChatRepository
from ..storage.document_repository import DocumentRepository
from ..storage.event_repository import EventRepository
from ..storage.search_repository import SearchRepository
from ..storage.relationship_repository import RelationshipRepository
from ..storage.revision_repository import RevisionRepository
from ..storage.state_repository import CharacterStateRepository
from ..storage.thread_repository import ThreadResolutionRepository
from ..storage.repositories import (
    AppSettingsRepository,
    GenerationRecord,
    GenerationRepository,
    ProjectRepository,
)
from ..storage.story_repositories import (
    ChapterRepository,
    CharacterRepository,
    SceneRepository,
    StoryBibleRepository,
)

WEB_DIR = Path(__file__).resolve().parents[1] / "web"
_SNIPPET_LENGTH = 280


# -- request models -------------------------------------------------------


class ProjectCreateRequest(BaseModel):
    name: str
    description: str = ""
    genre: str = ""
    narrative_style: str = ""
    target_word_count: int | None = None


class ProjectUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    genre: str | None = None
    narrative_style: str | None = None
    target_word_count: int | None = None


class BibleEntryCreateRequest(BaseModel):
    category: str
    title: str
    content: str = ""


class BibleEntryUpdateRequest(BaseModel):
    category: str | None = None
    title: str | None = None
    content: str | None = None


class CharacterCreateRequest(BaseModel):
    name: str
    aliases: list[str] = Field(default_factory=list)
    physical_description: str = ""
    age: str = ""
    personality: str = ""
    motivations: str = ""
    goals: str = ""
    fears: str = ""
    strengths: str = ""
    weaknesses: str = ""
    background: str = ""
    secrets: str = ""
    character_arc: str = ""


class CharacterUpdateRequest(BaseModel):
    name: str | None = None
    physical_description: str | None = None
    age: str | None = None
    personality: str | None = None
    motivations: str | None = None
    goals: str | None = None
    fears: str | None = None
    strengths: str | None = None
    weaknesses: str | None = None
    background: str | None = None
    secrets: str | None = None
    character_arc: str | None = None


class AliasesRequest(BaseModel):
    aliases: list[str] = Field(default_factory=list)


class ChapterCreateRequest(BaseModel):
    title: str
    position: int | None = None
    part: str = ""
    summary: str = ""
    objectives: str = ""
    viewpoint_character_id: int | None = None
    target_word_count: int | None = None
    status: str = "planned"
    content: str = ""
    origin: Literal["written", "imported"] = "written"


class ChapterUpdateRequest(BaseModel):
    title: str | None = None
    part: str | None = None
    summary: str | None = None
    objectives: str | None = None
    status: str | None = None
    viewpoint_character_id: int | None = None
    target_word_count: int | None = None
    content: str | None = None


class MoveRequest(BaseModel):
    direction: Literal["up", "down"]


class DocumentUpdateRequest(BaseModel):
    content: str = ""


class EventUpdateRequest(BaseModel):
    summary: str
    characters: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    objects: list[str] = Field(default_factory=list)
    threads: list[str] = Field(default_factory=list)


class CharacterStateCreateRequest(BaseModel):
    character_id: int
    chapter_id: int
    location: str = ""
    status: str = ""
    goals: str = ""
    knowledge: str = ""


class CharacterStateUpdateRequest(BaseModel):
    location: str = ""
    status: str = ""
    goals: str = ""
    knowledge: str = ""


class RelationshipCreateRequest(BaseModel):
    character_a_id: int
    character_b_id: int
    relation_type: str
    description: str = ""
    source_event_id: int | None = None


class RelationshipUpdateRequest(BaseModel):
    relation_type: str | None = None
    description: str | None = None


class RelationshipStatusRequest(BaseModel):
    status: str


class SummaryRequest(BaseModel):
    model: str = ""
    top_p: float = Field(default=0.9, gt=0.0, le=1.0)
    num_predict: int = Field(default=400, ge=32, le=8192)
    context_window: int = Field(default=4096, ge=512, le=32768)


class ChatThreadCreateRequest(BaseModel):
    mode: Literal["plan", "write"] = "plan"
    chapter_id: int | None = None
    title: str = ""


class ChatThreadUpdateRequest(BaseModel):
    planning_notes: str | None = None
    title: str | None = None
    mode: Literal["plan", "write"] | None = None


class ChatInsertRequest(BaseModel):
    replace: bool = False


class ChatMessageRequest(BaseModel):
    instructions: str
    model: str
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, gt=0.0, le=1.0)
    num_predict: int = Field(default=700, ge=32, le=8192)
    context_window: int = Field(default=4096, ge=512, le=32768)
    target_words: int = Field(default=900, ge=50, le=6000)


class ChatRevisionRequest(BaseModel):
    instructions: str
    model: str
    scope: str = "reply"
    message_id: int | None = None
    source_text: str = ""
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, gt=0.0, le=1.0)
    num_predict: int = Field(default=700, ge=32, le=8192)
    context_window: int = Field(default=4096, ge=512, le=32768)


class PlanDiscussionRequest(BaseModel):
    model: str
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, gt=0.0, le=1.0)
    num_predict: int = Field(default=700, ge=32, le=8192)
    context_window: int = Field(default=4096, ge=512, le=32768)


class StateUpdateItem(BaseModel):
    character_id: int
    location: str = ""
    status: str = ""
    goals: str = ""
    knowledge: str = ""


class StateUpdateApplyRequest(BaseModel):
    updates: list[StateUpdateItem] = Field(default_factory=list)


class ThreadStatusRequest(BaseModel):
    thread: str
    status: str = "resolved"
    note: str = ""
    chapter_id: int | None = None


class ContinuityCheckRequest(BaseModel):
    model: str
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, gt=0.0, le=1.0)
    num_predict: int = Field(default=700, ge=32, le=8192)
    context_window: int = Field(default=4096, ge=512, le=32768)


class ChapterReviewRequest(BaseModel):
    model: str
    draft: str | None = None
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, gt=0.0, le=1.0)
    num_predict: int = Field(default=700, ge=32, le=8192)
    context_window: int = Field(default=4096, ge=512, le=32768)


class SequenceDraftRequest(BaseModel):
    model: str
    instructions: str = ""
    target_words: int = Field(default=1200, ge=50, le=6000)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, gt=0.0, le=1.0)
    num_predict: int = Field(default=700, ge=32, le=8192)
    context_window: int = Field(default=4096, ge=512, le=32768)


class StyleGuideRequest(BaseModel):
    model: str = ""
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, gt=0.0, le=1.0)
    num_predict: int = Field(default=900, ge=32, le=8192)
    context_window: int = Field(default=4096, ge=512, le=32768)
    force: bool = False


class SceneCreateRequest(BaseModel):
    title: str = ""
    summary: str = ""
    objectives: str = ""
    content: str = ""
    status: str = "planned"


class SceneUpdateRequest(BaseModel):
    title: str | None = None
    summary: str | None = None
    objectives: str | None = None
    content: str | None = None
    status: str | None = None


class PlanChapterRequest(BaseModel):
    instructions: str = ""
    model: str
    temperature: float = Field(default=0.6, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, gt=0.0, le=1.0)
    num_predict: int = Field(default=700, ge=32, le=8192)
    context_window: int = Field(default=4096, ge=512, le=32768)


class GenerateRequest(BaseModel):
    instructions: str
    model: str
    temperature: float = Field(default=0.8, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, gt=0.0, le=1.0)
    num_predict: int = Field(default=700, ge=32, le=8192)
    context_window: int = Field(default=4096, ge=512, le=32768)
    target_words: int = 900
    chapter_title: str = ""
    scene_title: str = ""
    context_notes: str = ""
    chapter_id: int | None = None
    scene_id: int | None = None


# -- service wiring -------------------------------------------------------


@dataclass
class ApiServices:
    settings: Settings
    database: Database
    provider: LLMProvider
    projects: ProjectService
    projects_repository: ProjectRepository
    generation: GenerationService
    app_settings: AppSettingsService
    story_bible: StoryBibleService
    characters: CharacterService
    chapters: ChapterService
    scenes: SceneService
    documents: ProjectDocumentService
    outline: OutlineService
    analysis: ChapterAnalysisService
    export: ExportService
    context: GenerationContextBuilder
    style_guide: StyleGuideService
    summaries: ChapterSummaryService
    memory: MemoryService
    events: EventExtractionService
    event_repository: EventRepository
    relationships: RelationshipService
    character_states: CharacterStateService
    backup: BackupService
    generations: GenerationRepository
    insights: ChapterInsightService
    insight_repository: ChapterInsightRepository
    analysis_state: AnalysisStateRepository
    analysis_scheduler: AnalysisScheduler
    chat: ChatService
    orchestration: ChapterDraftSequence
    review: ChapterReviewService
    discussion: ChapterDiscussionService
    continuity: ContinuityCheckService
    ledger: ContinuityLedgerService
    threads: ThreadService
    state_proposals: CharacterStateProposalService


def build_services(
    settings: Settings, database: Database, provider: LLMProvider
) -> ApiServices:
    provider = SerializedProvider(provider)
    project_repository = ProjectRepository(database)
    generation_repository = GenerationRepository(database)
    character_repository = CharacterRepository(database)
    chapter_repository = ChapterRepository(database)
    bible_repository = StoryBibleRepository(database)
    event_repository = EventRepository(database)
    relationship_repository = RelationshipRepository(database)
    state_repository = CharacterStateRepository(database)
    thread_repository = ThreadResolutionRepository(database)
    insight_repository = ChapterInsightRepository(database)
    analysis_state_repository = AnalysisStateRepository(database)
    chapter_service = ChapterService(
        chapter_repository,
        project_repository,
        character_repository,
        state_repository,
        RevisionRepository(database),
    )
    document_service = ProjectDocumentService(
        DocumentRepository(database), project_repository
    )
    summary_service = ChapterSummaryService(
        provider, project_repository, chapter_service
    )
    event_service = EventExtractionService(
        provider,
        project_repository,
        chapter_service,
        event_repository,
        character_repository,
    )
    insight_service = ChapterInsightService(
        provider,
        project_repository,
        chapter_service,
        character_repository,
        insight_repository,
    )
    analysis_service = ChapterAnalysisService(
        summary_service,
        event_service,
        insight_service,
        chapter_service,
        event_repository,
        insight_repository,
        analysis_state_repository,
    )
    app_settings_service = AppSettingsService(
        AppSettingsRepository(database), settings.generation
    )
    analysis_scheduler = AnalysisScheduler(
        analysis_service,
        analysis_state_repository,
        app_settings_service.generation_settings,
        auto_run=settings.analysis.auto_run,
    )
    context_builder = GenerationContextBuilder(
        document_service,
        bible_repository,
        character_repository,
        chapter_repository,
        SearchRepository(database),
        event_repository,
        relationship_repository,
        state_repository,
    )
    chat_service = ChatService(
        provider,
        project_repository,
        chapter_service,
        ChatRepository(database),
        context_builder,
    )
    generation_service = GenerationService(
        provider, project_repository, generation_repository
    )
    state_service = CharacterStateService(
        project_repository,
        character_repository,
        chapter_repository,
        state_repository,
    )

    return ApiServices(
        settings=settings,
        database=database,
        provider=provider,
        projects=ProjectService(project_repository),
        projects_repository=project_repository,
        generation=generation_service,
        app_settings=app_settings_service,
        story_bible=StoryBibleService(bible_repository, project_repository),
        characters=CharacterService(character_repository, project_repository),
        chapters=chapter_service,
        scenes=SceneService(SceneRepository(database), chapter_repository),
        documents=document_service,
        outline=OutlineService(document_service, chapter_service),
        analysis=analysis_service,
        export=ExportService(
            project_repository, chapter_service, document_service
        ),
        summaries=summary_service,
        memory=MemoryService(SearchRepository(database), project_repository),
        events=event_service,
        event_repository=event_repository,
        relationships=RelationshipService(
            project_repository,
            character_repository,
            event_repository,
            relationship_repository,
        ),
        character_states=state_service,
        state_proposals=CharacterStateProposalService(
            provider,
            project_repository,
            chapter_repository,
            character_repository,
            state_repository,
            state_service,
        ),
        backup=BackupService(database),
        context=context_builder,
        style_guide=StyleGuideService(
            provider, project_repository, chapter_service, document_service
        ),
        generations=generation_repository,
        insights=insight_service,
        insight_repository=insight_repository,
        analysis_state=analysis_state_repository,
        analysis_scheduler=analysis_scheduler,
        chat=chat_service,
        orchestration=ChapterDraftSequence(generation_service, context_builder),
        review=ChapterReviewService(
            provider, project_repository, chapter_service, context_builder
        ),
        discussion=ChapterDiscussionService(
            provider, project_repository, chapter_service, context_builder
        ),
        continuity=ContinuityCheckService(
            provider,
            project_repository,
            chapter_repository,
            character_repository,
            state_repository,
            relationship_repository,
            event_repository,
            bible_repository,
        ),
        ledger=ContinuityLedgerService(
            project_repository,
            chapter_repository,
            character_repository,
            state_repository,
            event_repository,
            thread_repository,
        ),
        threads=ThreadService(
            project_repository, chapter_repository, thread_repository
        ),
    )


# -- serialization helpers ------------------------------------------------


def generation_payload(
    record: GenerationRecord, *, include_output: bool = False
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": record.id,
        "project_id": record.project_id,
        "model": record.model,
        "status": record.status,
        "word_count": record.word_count,
        "duration_ms": record.duration_ms,
        "truncated": record.truncated,
        "error": record.error,
        "temperature": record.temperature,
        "top_p": record.top_p,
        "num_predict": record.num_predict,
        "context_window": record.context_window,
        "created_at": record.created_at,
    }
    if include_output:
        payload["output"] = record.output
    else:
        payload["excerpt"] = record.output[:_SNIPPET_LENGTH]
    return payload


def _status_code_for(exc: NovellireError) -> int:
    if isinstance(exc, (ProjectNotFoundError, RecordNotFoundError)):
        return 404
    if isinstance(exc, (DuplicateProjectError, DuplicateEntryError)):
        return 409
    if isinstance(exc, LLMError):
        return 502
    return 400


# -- application factory --------------------------------------------------


def create_app(
    *,
    settings: Settings | None = None,
    database: Database | None = None,
    provider: LLMProvider | None = None,
) -> FastAPI:
    """Build the application.

    Optional arguments exist for tests and for embedding; production uses the
    configured settings, database, and Ollama provider.
    """
    resolved_settings = settings or load_settings()
    configure_logging(resolved_settings.log_level)

    resolved_database = database or Database(resolved_settings.database_path)
    resolved_database.initialize()

    resolved_provider = provider or OllamaProvider(
        base_url=resolved_settings.ollama.base_url,
        request_timeout=resolved_settings.ollama.request_timeout_seconds,
        connect_timeout=resolved_settings.ollama.connect_timeout_seconds,
        keep_alive=resolved_settings.ollama.keep_alive,
    )
    services = build_services(resolved_settings, resolved_database, resolved_provider)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        services.analysis_scheduler.start()
        try:
            yield
        finally:
            services.analysis_scheduler.stop()

    app = FastAPI(
        title="Novellire",
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.services = services
    app.include_router(_build_router(services))
    _register_error_handlers(app)

    if WEB_DIR.is_dir():
        @app.middleware("http")
        async def revalidate_static_assets(request, call_next):
            """Keep upgrades from serving a stale browser module."""
            response = await call_next(request)
            is_static = request.url.path.startswith("/static/")
            is_html = response.headers.get("content-type", "").startswith(
                "text/html"
            )
            if is_static or is_html:
                response.headers.setdefault("Cache-Control", "no-store")
            return response

        app.mount(
            "/static", StaticFiles(directory=WEB_DIR / "static"), name="static"
        )

        @app.get("/{full_path:path}", include_in_schema=False)
        def serve_client(full_path: str) -> FileResponse:
            if full_path.startswith("api"):
                raise HTTPException(status_code=404, detail="Unknown API route.")
            candidate = (WEB_DIR / full_path).resolve()
            if full_path and candidate.is_file() and WEB_DIR in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(WEB_DIR / "index.html")

    return app


def _register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(NovellireError)
    async def handle_novellire_error(_request, exc: NovellireError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=_status_code_for(exc))


def _build_router(services: ApiServices) -> APIRouter:
    router = APIRouter(prefix="/api")
    settings = services.settings

    @router.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": __version__,
            "schema_version": services.database.schema_version(),
        }

    @router.get("/meta")
    def meta() -> dict[str, Any]:
        return {
            "version": __version__,
            "bible_categories": [
                {"key": key, "label": label}
                for key, label in STORY_BIBLE_CATEGORIES
            ],
            "work_statuses": [
                {"key": key, "label": WORK_STATUS_LABELS[key]}
                for key in WORK_STATUSES
            ],
            "character_fields": [
                {"key": field, "label": CHARACTER_FIELD_LABELS[field]}
                for field in PROFILE_FIELDS
            ],
            "relationship_types": [
                {"key": key, "label": label}
                for key, label in RELATIONSHIP_TYPE_LABELS.items()
            ],
            "appearance_options": {
                "themes": list(THEMES),
                "accents": list(ACCENTS),
                "ui_fonts": list(UI_FONTS),
                "reading_fonts": list(READING_FONTS),
                "reading_widths": list(READING_WIDTHS),
            },
            "workspace_documents": [
                {
                    "kind": item.kind,
                    "title": item.title,
                    "summary": item.summary,
                    "placeholder": item.placeholder,
                }
                for item in WORKSPACE_DOCUMENTS
            ],
        }

    @router.get("/settings")
    def get_settings() -> dict[str, Any]:
        return {
            "generation": services.app_settings.generation_settings().model_dump(),
            "appearance": services.app_settings.appearance().model_dump(),
            "provider": {
                "kind": "ollama",
                "base_url": settings.ollama.base_url,
                "request_timeout_seconds": settings.ollama.request_timeout_seconds,
            },
            "paths": {
                "data_dir": str(settings.data_dir),
                "database": str(services.database.path),
            },
            "version": __version__,
            "schema_version": services.database.schema_version(),
        }

    @router.put("/settings/generation")
    def save_generation_settings(
        payload: GenerationSettings,
    ) -> dict[str, Any]:
        services.app_settings.save_generation_settings(payload)
        return payload.model_dump()

    @router.put("/settings/appearance")
    def save_appearance(payload: AppearanceSettings) -> dict[str, Any]:
        services.app_settings.save_appearance(payload)
        return payload.model_dump()

    @router.get("/ollama/status")
    def ollama_status() -> dict[str, Any]:
        available = False
        models: list[dict[str, Any]] = []
        error: str | None = None
        try:
            available = services.provider.is_available()
            if available:
                models = [asdict(model) for model in services.provider.list_models()]
        except NovellireError as exc:
            available = False
            error = str(exc)
        return {
            "available": available,
            "base_url": settings.ollama.base_url,
            "models": models,
            "error": error,
        }

    # -- projects ------------------------------------------------------

    @router.get("/projects")
    def list_projects() -> dict[str, Any]:
        active_id = services.app_settings.active_project_id()
        payload = []
        for project in services.projects.list_projects():
            payload.append(
                {
                    **asdict(project),
                    "words_generated": services.generations.produced_words(project.id),
                    "generations": services.generations.count_for_project(project.id),
                }
            )
        return {"projects": payload, "active_project_id": active_id}

    @router.post("/projects", status_code=201)
    def create_project(payload: ProjectCreateRequest) -> dict[str, Any]:
        project = services.projects.create_project(
            name=payload.name,
            description=payload.description,
            genre=payload.genre,
            narrative_style=payload.narrative_style,
            target_word_count=payload.target_word_count,
        )
        services.app_settings.set_active_project_id(project.id)
        return asdict(project)

    @router.patch("/projects/{project_id}")
    def update_project(project_id: int, payload: ProjectUpdateRequest) -> dict[str, Any]:
        data = payload.model_dump(exclude_unset=True)
        project = services.projects.update_project(
            project_id,
            description=data.get("description"),
            genre=data.get("genre"),
            narrative_style=data.get("narrative_style"),
            target_word_count=data.get("target_word_count"),
        )
        if data.get("name"):
            project = services.projects.rename_project(project_id, data["name"])
        return asdict(project)

    @router.post("/projects/{project_id}/archive")
    def archive_project(project_id: int) -> dict[str, Any]:
        project = services.projects.archive_project(project_id)
        if services.app_settings.active_project_id() == project_id:
            services.app_settings.set_active_project_id(None)
        return asdict(project)

    @router.post("/projects/{project_id}/activate")
    def activate_project(project_id: int) -> dict[str, Any]:
        services.projects.require_project(project_id)
        services.app_settings.set_active_project_id(project_id)
        return {"active_project_id": project_id}

    # -- project tree and manuscript -----------------------------------

    @router.get("/projects/{project_id}/tree")
    def project_tree(project_id: int) -> dict[str, Any]:
        project = services.projects.require_project(project_id)
        chapters = []
        total_words = 0
        for chapter in services.chapters.list_chapters(project_id):
            total_words += chapter.word_count
            chapters.append(
                {
                    "id": chapter.id,
                    "position": chapter.position,
                    "title": chapter.title,
                    "status": chapter.status,
                    "word_count": chapter.word_count,
                    "origin": chapter.origin,
                    "scenes": [
                        {
                            "id": scene.id,
                            "position": scene.position,
                            "title": scene.title,
                            "word_count": scene.word_count,
                        }
                        for scene in services.scenes.list_scenes(chapter.id)
                    ],
                }
            )
        return {
            "project": asdict(project),
            "chapters": chapters,
            "stats": {"words": total_words, "chapters": len(chapters)},
        }

    @router.get("/projects/{project_id}/manuscript")
    def manuscript(project_id: int) -> dict[str, Any]:
        project = services.projects.require_project(project_id)
        chapters = [
            asdict(chapter)
            for chapter in services.chapters.list_chapters(project_id)
        ]
        return {"project": asdict(project), "chapters": chapters}

    # -- workspace documents -------------------------------------------

    @router.get("/projects/{project_id}/documents")
    def list_documents(project_id: int) -> list[dict[str, Any]]:
        return services.documents.list_documents(project_id)

    @router.put("/projects/{project_id}/documents/{kind}")
    def save_document(
        project_id: int, kind: str, payload: DocumentUpdateRequest
    ) -> dict[str, Any]:
        document = services.documents.save_document(project_id, kind, payload.content)
        services.analysis_scheduler.schedule_document(
            project_id, document.kind, document.content
        )
        definition = next(
            item for item in WORKSPACE_DOCUMENTS if item.kind == document.kind
        )
        return {
            "kind": document.kind,
            "title": definition.title,
            "content": document.content,
            "derived": document.derived,
            "updated_at": document.updated_at,
        }

    @router.get("/projects/{project_id}/analysis/status")
    def analysis_status(project_id: int) -> dict[str, Any]:
        services.projects.require_project(project_id)
        states = services.analysis_state.list_for_project(project_id)
        counts: dict[str, int] = {}
        for state in states:
            counts[state.status] = counts.get(state.status, 0) + 1
        return {
            "counts": counts,
            "states": [asdict(state) for state in states],
        }

    # -- chat ----------------------------------------------------------

    @router.get("/projects/{project_id}/chat/threads")
    def list_chat_threads(project_id: int) -> list[dict[str, Any]]:
        return [asdict(thread) for thread in services.chat.list_threads(project_id)]

    @router.post("/projects/{project_id}/chat/threads", status_code=201)
    def create_chat_thread(
        project_id: int, payload: ChatThreadCreateRequest
    ) -> dict[str, Any]:
        thread = services.chat.create_thread(
            project_id=project_id,
            mode=payload.mode,
            chapter_id=payload.chapter_id,
            title=payload.title,
        )
        return asdict(thread)

    @router.get("/chat/threads/{thread_id}")
    def get_chat_thread(thread_id: int) -> dict[str, Any]:
        bundle = services.chat.get_thread_bundle(thread_id)
        return {
            "thread": asdict(bundle.thread),
            "messages": [asdict(message) for message in bundle.messages],
            "draft": asdict(bundle.draft) if bundle.draft is not None else None,
        }

    @router.patch("/chat/threads/{thread_id}")
    def update_chat_thread(
        thread_id: int, payload: ChatThreadUpdateRequest
    ) -> dict[str, Any]:
        thread = services.chat.update_thread(
            thread_id,
            planning_notes=payload.planning_notes,
            title=payload.title,
            mode=payload.mode,
        )
        return asdict(thread)

    @router.post("/chat/threads/{thread_id}/messages")
    def send_chat_message(
        thread_id: int, payload: ChatMessageRequest
    ) -> dict[str, Any]:
        settings = GenerationSettings(
            model=payload.model,
            temperature=payload.temperature,
            top_p=payload.top_p,
            num_predict=payload.num_predict,
            context_window=payload.context_window,
        )
        reply = services.chat.send_message(
            thread_id,
            instructions=payload.instructions,
            settings=settings,
            target_words=payload.target_words,
        )
        return {
            "thread": asdict(reply.thread),
            "user": asdict(reply.user_message),
            "assistant": asdict(reply.assistant_message),
            "context": {
                "chapters": list(reply.context_chapters),
                "events": reply.context_events,
            },
        }

    @router.post("/chat/threads/{thread_id}/messages/stream")
    def stream_chat_message(
        thread_id: int, payload: ChatMessageRequest
    ) -> StreamingResponse:
        """Stream one chat reply as newline-delimited JSON events.

        ``start`` carries the stored author message, ``delta`` carries text as it
        arrives, ``done`` carries the stored reply and updated thread, and
        ``error`` reports a failure without a stack trace reaching the client.
        """
        settings = GenerationSettings(
            model=payload.model,
            temperature=payload.temperature,
            top_p=payload.top_p,
            num_predict=payload.num_predict,
            context_window=payload.context_window,
        )
        events = services.chat.stream_message(
            thread_id,
            instructions=payload.instructions,
            settings=settings,
            target_words=payload.target_words,
        )

        def lines() -> Iterator[str]:
            for event in events:
                yield json.dumps(event, ensure_ascii=False) + "\n"

        return StreamingResponse(
            lines(),
            media_type="application/x-ndjson",
            headers={
                "Cache-Control": "no-store",
                "X-Accel-Buffering": "no",
            },
        )

    @router.post("/chat/threads/{thread_id}/revisions")
    def revise_chat_message(
        thread_id: int, payload: ChatRevisionRequest
    ) -> dict[str, Any]:
        """Revise a reply or the chapter into a new, comparable message."""
        reply = services.chat.revise_message(
            thread_id,
            scope=payload.scope,
            message_id=payload.message_id,
            instructions=payload.instructions,
            source_text=payload.source_text,
            settings=GenerationSettings(
                model=payload.model,
                temperature=payload.temperature,
                top_p=payload.top_p,
                num_predict=payload.num_predict,
                context_window=payload.context_window,
            ),
        )
        return {
            "thread": asdict(reply.thread),
            "user": asdict(reply.user_message),
            "assistant": asdict(reply.assistant_message),
            "context": {
                "chapters": list(reply.context_chapters),
                "events": reply.context_events,
            },
        }

    @router.post("/chat/threads/{thread_id}/revisions/stream")
    def stream_chat_revision(
        thread_id: int, payload: ChatRevisionRequest
    ) -> StreamingResponse:
        """Stream one revision as newline-delimited JSON events."""
        settings = GenerationSettings(
            model=payload.model,
            temperature=payload.temperature,
            top_p=payload.top_p,
            num_predict=payload.num_predict,
            context_window=payload.context_window,
        )
        events = services.chat.stream_revision(
            thread_id,
            scope=payload.scope,
            message_id=payload.message_id,
            instructions=payload.instructions,
            settings=settings,
            source_text=payload.source_text,
        )

        def lines() -> Iterator[str]:
            for event in events:
                yield json.dumps(event, ensure_ascii=False) + "\n"

        return StreamingResponse(
            lines(),
            media_type="application/x-ndjson",
            headers={
                "Cache-Control": "no-store",
                "X-Accel-Buffering": "no",
            },
        )

    @router.post("/chat/threads/{thread_id}/draft/recover")
    def recover_chat_draft(thread_id: int) -> dict[str, Any]:
        """Keep the checkpoint of an interrupted reply as a model message."""
        return asdict(services.chat.recover_draft(thread_id))

    @router.delete("/chat/threads/{thread_id}/draft")
    def discard_chat_draft(thread_id: int) -> dict[str, Any]:
        services.chat.discard_draft(thread_id)
        return {"deleted": True}

    @router.post("/chat/threads/{thread_id}/messages/{message_id}/insert")
    def insert_chat_message(
        thread_id: int,
        message_id: int,
        payload: ChatInsertRequest | None = None,
    ) -> dict[str, Any]:
        """Append or replace the chapter text with a Write-mode reply."""
        chapter = services.chat.insert_reply(
            thread_id,
            message_id,
            replace=bool(payload and payload.replace),
        )
        services.analysis_scheduler.schedule_chapter(chapter)
        return asdict(chapter)

    @router.get("/projects/{project_id}/insights")
    def list_project_insights(project_id: int) -> list[dict[str, Any]]:
        services.projects.require_project(project_id)
        chapters = {
            chapter.id: chapter
            for chapter in services.chapters.list_chapters(project_id)
        }
        payloads = []
        for record in services.insight_repository.list_for_project(project_id):
            payload = asdict(record)
            chapter = chapters.get(record.chapter_id)
            payload["chapter_title"] = chapter.title if chapter else ""
            payload["chapter_position"] = chapter.position if chapter else 0
            payloads.append(payload)
        return payloads

    @router.get("/chapters/{chapter_id}/insights")
    def get_chapter_insights(chapter_id: int) -> dict[str, Any]:
        record = services.insight_repository.get_for_chapter(chapter_id)
        if record is None:
            raise RecordNotFoundError(
                "No derived insights exist for this chapter yet."
            )
        return asdict(record)

    @router.get("/projects/{project_id}/outline/preview")
    def preview_outline(project_id: int) -> dict[str, Any]:
        preview = services.outline.preview(project_id)
        return {
            "chapters": [asdict(item) for item in preview.items],
            "create_count": preview.create_count,
            "existing_count": preview.existing_count,
            "analysis_count": preview.analysis_count,
        }

    @router.post("/projects/{project_id}/outline/apply")
    def apply_outline(project_id: int) -> dict[str, Any]:
        result = services.outline.apply(project_id)
        return {
            "created": [asdict(chapter) for chapter in result.created],
            "created_count": len(result.created),
            "existing_count": result.existing_count,
        }

    @router.post("/projects/{project_id}/outline/analyze")
    def analyze_outline_chapters(
        project_id: int, payload: SummaryRequest
    ) -> StreamingResponse:
        """Analyse every written chapter missing memory, sequentially."""
        services.projects.require_project(project_id)
        defaults = services.app_settings.generation_settings()
        settings = GenerationSettings(
            model=payload.model or defaults.model,
            temperature=0.2,
            top_p=payload.top_p,
            num_predict=payload.num_predict,
            context_window=payload.context_window,
        )
        chapters = [
            chapter
            for chapter in services.chapters.list_chapters(project_id)
            if chapter.content.strip()
        ]
        written_ids = {chapter.id for chapter in chapters}

        def event_line(event: dict[str, Any]) -> str:
            return json.dumps(event, ensure_ascii=False) + "\n"

        def events() -> Iterator[str]:
            yield event_line(
                {"type": "start", "total": len(chapters)}
            )
            counts = {"analysed": 0, "skipped": 0, "empty": 0, "failed": 0}
            for step in services.analysis.analyze_project(project_id, settings):
                if step.chapter_id not in written_ids:
                    continue
                counts[step.status] = counts.get(step.status, 0) + 1
                yield event_line(
                    {
                        "type": "step",
                        "chapter_id": step.chapter_id,
                        "title": step.title,
                        "position": step.position,
                        "status": step.status,
                        "detail": step.detail,
                        "duration_ms": step.duration_ms,
                        "processed": sum(counts.values()),
                        "total": len(chapters),
                    }
                )
            yield event_line(
                {"type": "done", **counts, "total": len(chapters)}
            )

        return StreamingResponse(
            events(),
            media_type="application/x-ndjson",
            headers={
                "Cache-Control": "no-store",
                "X-Accel-Buffering": "no",
            },
        )

    @router.post("/projects/{project_id}/style-guide/analyze")
    def analyze_style_guide(
        project_id: int, payload: StyleGuideRequest
    ) -> dict[str, Any]:
        defaults = services.app_settings.generation_settings()
        outcome = services.style_guide.analyze(
            project_id,
            GenerationSettings(
                model=payload.model or defaults.model,
                temperature=payload.temperature,
                top_p=payload.top_p,
                num_predict=payload.num_predict,
                context_window=payload.context_window,
            ),
            force=payload.force,
        )
        return {
            "content": outcome.content,
            "model": outcome.model,
            "word_count": outcome.word_count,
            "duration_ms": outcome.duration_ms,
            "derived": True,
        }

    # -- memory --------------------------------------------------------

    @router.get("/projects/{project_id}/search")
    def search_project(
        project_id: int,
        q: str = Query(min_length=1),
        limit: int = Query(default=20, ge=1, le=50),
    ) -> dict[str, Any]:
        hits = services.memory.search(project_id, q, limit=limit)
        return {
            "query": q,
            "results": [
                {
                    "kind": hit.kind,
                    "title": hit.title,
                    "source_id": hit.source_id,
                    "excerpt": hit.excerpt,
                }
                for hit in hits
            ],
        }

    # -- export --------------------------------------------------------

    @router.get("/projects/{project_id}/export")
    def export_project(
        project_id: int,
        export_format: Literal["markdown", "text"] = Query(
            default="markdown", alias="format"
        ),
        include_documents: bool = False,
    ) -> dict[str, Any]:
        result = services.export.build(
            project_id,
            file_format=export_format,
            include_documents=include_documents,
        )
        return {
            "filename": result.filename,
            "content": result.content,
            "format": result.file_format,
            "content_type": result.content_type,
            "word_count": result.word_count,
        }

    # -- story bible ---------------------------------------------------

    @router.get("/projects/{project_id}/bible")
    def list_bible(project_id: int, category: str | None = None) -> list[dict[str, Any]]:
        services.projects.require_project(project_id)
        return [
            asdict(entry)
            for entry in services.story_bible.list_entries(
                project_id, category=category
            )
        ]

    @router.post("/projects/{project_id}/bible", status_code=201)
    def create_bible_entry(
        project_id: int, payload: BibleEntryCreateRequest
    ) -> dict[str, Any]:
        entry = services.story_bible.create_entry(
            project_id=project_id,
            category=payload.category,
            title=payload.title,
            content=payload.content,
        )
        return asdict(entry)

    @router.patch("/bible/{entry_id}")
    def update_bible_entry(
        entry_id: int, payload: BibleEntryUpdateRequest
    ) -> dict[str, Any]:
        data = payload.model_dump(exclude_unset=True)
        entry = services.story_bible.update_entry(
            entry_id,
            category=data.get("category"),
            title=data.get("title"),
            content=data.get("content"),
        )
        return asdict(entry)

    # -- characters ----------------------------------------------------

    @router.get("/projects/{project_id}/characters")
    def list_characters(project_id: int) -> list[dict[str, Any]]:
        services.projects.require_project(project_id)
        return [
            asdict(character)
            for character in services.characters.list_characters(project_id)
        ]

    @router.post("/projects/{project_id}/characters", status_code=201)
    def create_character(
        project_id: int, payload: CharacterCreateRequest
    ) -> dict[str, Any]:
        data = payload.model_dump()
        character = services.characters.create_character(
            project_id=project_id,
            name=data.pop("name"),
            aliases=data.pop("aliases"),
            **{field: data[field] for field in PROFILE_FIELDS},
        )
        services.event_repository.reset_links(character.project_id)
        return asdict(character)

    @router.patch("/characters/{character_id}")
    def update_character(
        character_id: int, payload: CharacterUpdateRequest
    ) -> dict[str, Any]:
        data = payload.model_dump(exclude_unset=True)
        character = services.characters.update_character(
            character_id,
            name=data.pop("name", None),
            **{field: data[field] for field in PROFILE_FIELDS if field in data},
        )
        services.event_repository.reset_links(character.project_id)
        return asdict(character)

    @router.put("/characters/{character_id}/aliases")
    def set_aliases(character_id: int, payload: AliasesRequest) -> dict[str, Any]:
        character = services.characters.set_aliases(
            character_id, payload.aliases
        )
        services.event_repository.reset_links(character.project_id)
        return asdict(character)

    # -- chapters ------------------------------------------------------

    @router.get("/projects/{project_id}/chapters")
    def list_chapters(project_id: int) -> list[dict[str, Any]]:
        services.projects.require_project(project_id)
        return [
            asdict(chapter)
            for chapter in services.chapters.list_chapters(project_id)
        ]

    @router.post("/projects/{project_id}/chapters", status_code=201)
    def create_chapter(
        project_id: int, payload: ChapterCreateRequest
    ) -> dict[str, Any]:
        chapter = services.chapters.create_chapter(
            project_id=project_id,
            title=payload.title,
            position=payload.position,
            part=payload.part,
            summary=payload.summary,
            objectives=payload.objectives,
            viewpoint_character_id=payload.viewpoint_character_id,
            target_word_count=payload.target_word_count,
            status=payload.status,
            content=payload.content,
            origin=payload.origin,
        )
        services.analysis_scheduler.schedule_chapter(chapter)
        return asdict(chapter)

    @router.patch("/chapters/{chapter_id}")
    def update_chapter(
        chapter_id: int, payload: ChapterUpdateRequest
    ) -> dict[str, Any]:
        data = payload.model_dump(exclude_unset=True)
        kwargs: dict[str, Any] = {}
        for key in ("title", "part", "summary", "objectives", "status", "content"):
            if key in data and data[key] is not None:
                kwargs[key] = data[key]
        if "viewpoint_character_id" in data:
            kwargs["viewpoint_character_id"] = data["viewpoint_character_id"]
        if "target_word_count" in data:
            kwargs["target_word_count"] = data["target_word_count"]
        chapter = services.chapters.update_chapter(chapter_id, **kwargs)
        services.analysis_scheduler.schedule_chapter(chapter)
        return asdict(chapter)

    @router.get("/chapters/{chapter_id}/revisions")
    def list_chapter_revisions(chapter_id: int) -> list[dict[str, Any]]:
        return [
            {
                "id": revision.id,
                "chapter_id": revision.chapter_id,
                "title": revision.title,
                "word_count": revision.word_count,
                "source": revision.source,
                "created_at": revision.created_at,
                "excerpt": " ".join(revision.content.split())[:240],
            }
            for revision in services.chapters.list_revisions(chapter_id)
        ]

    @router.get("/chapters/{chapter_id}/revisions/{revision_id}")
    def get_chapter_revision(
        chapter_id: int, revision_id: int
    ) -> dict[str, Any]:
        revision = services.chapters.get_revision(chapter_id, revision_id)
        return asdict(revision)

    @router.post("/chapters/{chapter_id}/revisions/{revision_id}/restore")
    def restore_chapter_revision(
        chapter_id: int, revision_id: int
    ) -> dict[str, Any]:
        return asdict(
            services.chapters.restore_revision(chapter_id, revision_id)
        )

    @router.post("/projects/{project_id}/summaries")
    def summarize_project(
        project_id: int, payload: SummaryRequest
    ) -> StreamingResponse:
        """Summarise every pending chapter sequentially, streaming progress."""
        services.projects.require_project(project_id)
        defaults = services.app_settings.generation_settings()
        settings = GenerationSettings(
            model=payload.model or defaults.model,
            temperature=0.2,
            top_p=payload.top_p,
            num_predict=payload.num_predict,
            context_window=payload.context_window,
        )
        chapters = services.chapters.list_chapters(project_id)
        pending = sum(
            1
            for chapter in chapters
            if chapter.content.strip() and not chapter.summary.strip()
        )

        def event_line(event: dict[str, Any]) -> str:
            return json.dumps(event, ensure_ascii=False) + "\n"

        def events() -> Iterator[str]:
            yield event_line(
                {"type": "start", "total": len(chapters), "pending": pending}
            )
            counts = {"summarised": 0, "skipped": 0, "empty": 0, "failed": 0}
            for step in services.summaries.summarize_pending(project_id, settings):
                counts[step.status] = counts.get(step.status, 0) + 1
                yield event_line(
                    {
                        "type": "step",
                        "chapter_id": step.chapter_id,
                        "title": step.title,
                        "position": step.position,
                        "status": step.status,
                        "detail": step.detail,
                        "duration_ms": step.duration_ms,
                        "processed": sum(counts.values()),
                    }
                )
            yield event_line({"type": "done", **counts, "total": len(chapters)})

        return StreamingResponse(
            events(),
            media_type="application/x-ndjson",
            headers={
                "Cache-Control": "no-store",
                "X-Accel-Buffering": "no",
            },
        )

    @router.post("/chapters/{chapter_id}/summarize")
    def summarize_chapter(
        chapter_id: int, payload: SummaryRequest
    ) -> dict[str, Any]:
        defaults = services.app_settings.generation_settings()
        outcome = services.summaries.summarize(
            chapter_id,
            GenerationSettings(
                model=payload.model or defaults.model,
                temperature=0.2,
                top_p=payload.top_p,
                num_predict=payload.num_predict,
                context_window=payload.context_window,
            ),
        )
        return {
            **asdict(outcome.chapter),
            "model": outcome.model,
            "duration_ms": outcome.duration_ms,
        }

    @router.post("/chapters/{chapter_id}/events/extract")
    def extract_events(
        chapter_id: int, payload: SummaryRequest
    ) -> dict[str, Any]:
        defaults = services.app_settings.generation_settings()
        outcome = services.events.extract(
            chapter_id,
            GenerationSettings(
                model=payload.model or defaults.model,
                temperature=0.1,
                top_p=payload.top_p,
                num_predict=payload.num_predict,
                context_window=payload.context_window,
            ),
        )
        return {
            "events": [asdict(event) for event in outcome.events],
            "model": outcome.model,
            "duration_ms": outcome.duration_ms,
        }

    @router.get("/projects/{project_id}/events")
    def list_events(project_id: int) -> list[dict[str, Any]]:
        services.projects.require_project(project_id)
        services.events.ensure_links(project_id)
        return [
            asdict(event)
            for event in services.event_repository.list_for_project(project_id)
        ]

    @router.patch("/events/{event_id}")
    def update_event(
        event_id: int, payload: EventUpdateRequest
    ) -> dict[str, Any]:
        event = services.events.update_event(
            event_id,
            summary=payload.summary,
            characters=payload.characters,
            locations=payload.locations,
            objects=payload.objects,
            threads=payload.threads,
        )
        return asdict(event)

    @router.delete("/events/{event_id}")
    def delete_event(event_id: int) -> dict[str, Any]:
        services.events.delete_event(event_id)
        return {"deleted": True}

    @router.get("/projects/{project_id}/relationships")
    def list_relationships(project_id: int) -> list[dict[str, Any]]:
        return [
            asdict(relationship)
            for relationship in services.events.relationships(project_id)
        ]

    @router.get("/projects/{project_id}/relationship-records")
    def list_relationship_records(project_id: int) -> list[dict[str, Any]]:
        return [
            asdict(record)
            for record in services.relationships.list_for_project(project_id)
        ]

    @router.post(
        "/projects/{project_id}/relationship-records", status_code=201
    )
    def create_relationship_record(
        project_id: int, payload: RelationshipCreateRequest
    ) -> dict[str, Any]:
        record = services.relationships.create(
            project_id,
            character_a_id=payload.character_a_id,
            character_b_id=payload.character_b_id,
            relation_type=payload.relation_type,
            description=payload.description,
            source_event_id=payload.source_event_id,
        )
        return asdict(record)

    @router.patch("/relationship-records/{record_id}")
    def update_relationship_record(
        record_id: int, payload: RelationshipUpdateRequest
    ) -> dict[str, Any]:
        data = payload.model_dump(exclude_unset=True)
        record = services.relationships.update(
            record_id,
            relation_type=data.get("relation_type"),
            description=data.get("description"),
        )
        return asdict(record)

    @router.patch("/relationship-records/{record_id}/status")
    def set_relationship_status(
        record_id: int, payload: RelationshipStatusRequest
    ) -> dict[str, Any]:
        return asdict(
            services.relationships.set_status(record_id, payload.status)
        )

    @router.delete("/relationship-records/{record_id}")
    def delete_relationship_record(record_id: int) -> dict[str, Any]:
        services.relationships.delete(record_id)
        return {"deleted": True}

    @router.get("/projects/{project_id}/character-states")
    def list_character_states(project_id: int) -> list[dict[str, Any]]:
        return [
            asdict(state)
            for state in services.character_states.list_for_project(project_id)
        ]

    @router.post("/projects/{project_id}/character-states", status_code=201)
    def create_character_state(
        project_id: int, payload: CharacterStateCreateRequest
    ) -> dict[str, Any]:
        state = services.character_states.create(
            project_id,
            character_id=payload.character_id,
            chapter_id=payload.chapter_id,
            location=payload.location,
            status=payload.status,
            goals=payload.goals,
            knowledge=payload.knowledge,
        )
        return asdict(state)

    @router.patch("/character-states/{state_id}")
    def update_character_state(
        state_id: int, payload: CharacterStateUpdateRequest
    ) -> dict[str, Any]:
        state = services.character_states.update(
            state_id,
            location=payload.location,
            status=payload.status,
            goals=payload.goals,
            knowledge=payload.knowledge,
        )
        return asdict(state)

    @router.delete("/character-states/{state_id}")
    def delete_character_state(state_id: int) -> dict[str, Any]:
        services.character_states.delete(state_id)
        return {"deleted": True}

    @router.post("/chapters/{chapter_id}/move")
    def move_chapter(chapter_id: int, payload: MoveRequest) -> dict[str, Any]:
        return asdict(services.chapters.move_chapter(chapter_id, payload.direction))

    @router.delete("/chapters/{chapter_id}")
    def delete_chapter(chapter_id: int) -> dict[str, Any]:
        services.chapters.delete_chapter(chapter_id)
        return {"deleted": True}

    # -- scenes --------------------------------------------------------

    @router.get("/chapters/{chapter_id}/scenes")
    def list_scenes(chapter_id: int) -> list[dict[str, Any]]:
        services.chapters.require_chapter(chapter_id)
        return [
            asdict(scene) for scene in services.scenes.list_scenes(chapter_id)
        ]

    @router.post("/chapters/{chapter_id}/scenes", status_code=201)
    def create_scene(chapter_id: int, payload: SceneCreateRequest) -> dict[str, Any]:
        scene = services.scenes.create_scene(
            chapter_id,
            title=payload.title,
            summary=payload.summary,
            objectives=payload.objectives,
            content=payload.content,
            status=payload.status,
        )
        return asdict(scene)

    @router.patch("/scenes/{scene_id}")
    def update_scene(scene_id: int, payload: SceneUpdateRequest) -> dict[str, Any]:
        data = payload.model_dump(exclude_unset=True)
        return asdict(services.scenes.update_scene(scene_id, **data))

    @router.post("/scenes/{scene_id}/move")
    def move_scene(scene_id: int, payload: MoveRequest) -> dict[str, Any]:
        return asdict(services.scenes.move_scene(scene_id, payload.direction))

    @router.delete("/scenes/{scene_id}")
    def delete_scene(scene_id: int) -> dict[str, Any]:
        services.scenes.delete_scene(scene_id)
        return {"deleted": True}

    # -- backup and restore --------------------------------------------

    @router.get("/backup")
    def download_backup() -> FileResponse:
        path, filename = services.backup.snapshot()
        return FileResponse(
            path,
            media_type="application/vnd.sqlite3",
            filename=filename,
            background=BackgroundTask(path.unlink, missing_ok=True),
        )

    @router.post("/backup/restore")
    async def restore_backup(request: Request) -> dict[str, Any]:
        outcome = services.backup.restore(await request.body())
        return {
            "restored": True,
            "projects": outcome.projects,
            "chapters": outcome.chapters,
            "safety_backup": outcome.safety_backup,
        }

    # -- generation ----------------------------------------------------

    @router.post("/projects/{project_id}/generate")
    def generate(project_id: int, payload: GenerateRequest) -> dict[str, Any]:
        chapter_title = payload.chapter_title
        scene_title = payload.scene_title
        if payload.chapter_id is not None:
            chapter = services.chapters.require_chapter(payload.chapter_id)
            if chapter.origin == "imported":
                raise InvalidInputError(
                    "That chapter is pre-written, so Novellire will not change it. "
                    "Generate into a new chapter instead."
                )
            chapter_title = chapter_title or chapter.title
        if payload.scene_id is not None:
            scene = services.scenes.require_scene(payload.scene_id)
            parent = services.chapters.require_chapter(scene.chapter_id)
            if parent.origin == "imported":
                raise InvalidInputError(
                    "That chapter is pre-written, so Novellire will not change it. "
                    "Generate into a new chapter instead."
                )
            scene_title = scene_title or scene.title

        inference_settings = GenerationSettings(
            model=payload.model,
            temperature=payload.temperature,
            top_p=payload.top_p,
            num_predict=payload.num_predict,
            context_window=payload.context_window,
        )

        style_guide_inferred = False
        guide = services.documents.get_document(project_id, "style_guide")
        if (
            (guide is None or not guide.content.strip())
            and services.style_guide.has_source_material(project_id)
        ):
            services.style_guide.analyze(project_id, inference_settings)
            style_guide_inferred = True

        generation_context = services.context.build(
            project_id,
            instructions=payload.instructions,
            chapter_id=payload.chapter_id,
            chapter_title=chapter_title or "",
            scene_title=scene_title or "",
            context_notes=payload.context_notes,
            context_window=payload.context_window,
            output_tokens=payload.num_predict,
        )

        outcome = services.generation.generate(
            project_id=project_id,
            instructions=payload.instructions,
            settings=inference_settings,
            chapter_title=chapter_title,
            scene_title=scene_title,
            context_notes=payload.context_notes,
            target_words=payload.target_words,
            context=generation_context,
        )
        result = generation_payload(outcome.record, include_output=True)
        result["style_guide_inferred"] = style_guide_inferred
        result["context"] = {
            "chapters": [
                asdict(source) for source in generation_context.memory_chapters
            ],
            "events": [
                asdict(event) for event in generation_context.memory_events
            ],
        }
        return result

    @router.post("/chapters/{chapter_id}/draft-sequence")
    def draft_chapter_sequence(
        chapter_id: int, payload: SequenceDraftRequest
    ) -> dict[str, Any]:
        """Draft a chapter scene by scene from its saved scene plan.

        The server owns the loop: one inference per beat, in order, assembled
        into one editable draft. The model never chooses what runs next, and the
        chapter is not changed until the author inserts the draft.
        """
        chapter = services.chapters.require_chapter(chapter_id)
        if chapter.origin == "imported":
            raise InvalidInputError(
                "That chapter is pre-written, so Novellire will not change it. "
                "Draft into a new chapter instead."
            )
        outcome = services.orchestration.draft(
            project_id=chapter.project_id,
            chapter=chapter,
            settings=GenerationSettings(
                model=payload.model,
                temperature=payload.temperature,
                top_p=payload.top_p,
                num_predict=payload.num_predict,
                context_window=payload.context_window,
            ),
            target_words=payload.target_words,
            instructions=payload.instructions,
        )
        return {
            "model": outcome.model,
            "output": outcome.text,
            "word_count": outcome.word_count,
            "truncated": False,
            "scenes": [
                {
                    "index": scene.index,
                    "beat": scene.beat,
                    "word_count": scene.word_count,
                    "model": scene.model,
                }
                for scene in outcome.scenes
            ],
            "context": {"chapters": [], "events": []},
        }

    @router.post("/chapters/{chapter_id}/state-proposals")
    def propose_state_updates(
        chapter_id: int, payload: PlanDiscussionRequest
    ) -> dict[str, Any]:
        """Propose character-state updates. Writes nothing until applied."""
        proposals = services.state_proposals.propose(
            chapter_id,
            settings=GenerationSettings(
                model=payload.model,
                temperature=payload.temperature,
                top_p=payload.top_p,
                num_predict=payload.num_predict,
                context_window=payload.context_window,
            ),
        )
        return {
            "proposals": [asdict(proposal) for proposal in proposals],
            "model": payload.model,
        }

    @router.post("/chapters/{chapter_id}/state-proposals/apply")
    def apply_state_updates(
        chapter_id: int, payload: StateUpdateApplyRequest
    ) -> dict[str, Any]:
        """Apply reviewed proposals as snapshots for this chapter."""
        states = services.state_proposals.apply(
            chapter_id,
            [
                StateUpdateInput(
                    character_id=update.character_id,
                    location=update.location,
                    status=update.status,
                    goals=update.goals,
                    knowledge=update.knowledge,
                )
                for update in payload.updates
            ],
        )
        return {"states": [asdict(state) for state in states]}

    @router.put("/projects/{project_id}/threads")
    def set_thread_status(
        project_id: int, payload: ThreadStatusRequest
    ) -> dict[str, Any]:
        """Resolve a recorded thread, or reopen it. The events stay untouched."""
        resolution = services.threads.set_status(
            project_id,
            thread=payload.thread,
            status=payload.status,
            note=payload.note,
            chapter_id=payload.chapter_id,
        )
        return {
            "status": "resolved" if resolution is not None else "open",
            "resolution": asdict(resolution) if resolution is not None else None,
        }

    @router.get("/projects/{project_id}/continuity")
    def get_continuity_ledger(project_id: int) -> dict[str, Any]:
        """Recorded timeline, knowledge changes, and unresolved threads."""
        return services.ledger.ledger(project_id)

    @router.post("/chapters/{chapter_id}/continuity")
    def check_chapter_continuity(
        chapter_id: int, payload: ContinuityCheckRequest
    ) -> dict[str, Any]:
        """Check a saved chapter against cited canon. Read-only."""
        result = services.continuity.check(
            chapter_id,
            settings=GenerationSettings(
                model=payload.model,
                temperature=payload.temperature,
                top_p=payload.top_p,
                num_predict=payload.num_predict,
                context_window=payload.context_window,
            ),
        )
        return {
            "canon_count": result.canon_count,
            "model": result.model,
            "findings": [asdict(finding) for finding in result.findings],
        }

    @router.post("/chapters/{chapter_id}/discuss")
    def discuss_chapter_plan(
        chapter_id: int, payload: PlanDiscussionRequest
    ) -> dict[str, Any]:
        """Ask what the saved scene plan still leaves undecided.

        Read-only: the plan is not rewritten and no prose is generated. The
        author's answers are passed to the draft, never stored as canon.
        """
        result = services.discussion.discuss(
            chapter_id,
            settings=GenerationSettings(
                model=payload.model,
                temperature=payload.temperature,
                top_p=payload.top_p,
                num_predict=payload.num_predict,
                context_window=payload.context_window,
            ),
        )
        return {
            "ready": result.ready,
            "summary": result.summary,
            "model": result.model,
            "questions": [asdict(question) for question in result.questions],
        }

    @router.post("/chapters/{chapter_id}/review")
    def review_chapter(
        chapter_id: int, payload: ChapterReviewRequest
    ) -> dict[str, Any]:
        """Review a draft against the plan and canon and propose edits.

        The review is read-only. Readings are one inference; every finding must
        quote the reviewed text exactly once, and the model executes nothing.
        """
        result = services.review.review(
            chapter_id,
            settings=GenerationSettings(
                model=payload.model,
                temperature=payload.temperature,
                top_p=payload.top_p,
                num_predict=payload.num_predict,
                context_window=payload.context_window,
            ),
            draft=payload.draft,
        )
        return {
            "source": result.source,
            "overall": result.overall,
            "model": result.model,
            "reviewed_chars": result.reviewed_chars,
            "findings": [asdict(finding) for finding in result.findings],
        }

    @router.post("/chapters/{chapter_id}/plan")
    def plan_chapter(
        chapter_id: int, payload: PlanChapterRequest
    ) -> dict[str, Any]:
        chapter = services.chapters.require_chapter(chapter_id)
        if chapter.origin == "imported":
            raise InvalidInputError(
                "That chapter is pre-written, so there is nothing to plan."
            )
        inference_settings = GenerationSettings(
            model=payload.model,
            temperature=payload.temperature,
            top_p=payload.top_p,
            num_predict=payload.num_predict,
            context_window=payload.context_window,
        )
        generation_context = services.context.build(
            chapter.project_id,
            instructions=payload.instructions,
            chapter_id=chapter.id,
            chapter_title=chapter.title,
            context_window=payload.context_window,
            output_tokens=payload.num_predict,
        )
        outcome = services.generation.generate_plan(
            project_id=chapter.project_id,
            instructions=payload.instructions,
            settings=inference_settings,
            chapter_title=chapter.title,
            chapter_summary=chapter.summary,
            chapter_plan=chapter.objectives,
            context=generation_context,
        )
        result = generation_payload(outcome.record, include_output=True)
        result["context"] = {
            "chapters": [
                asdict(source) for source in generation_context.memory_chapters
            ],
            "events": [
                asdict(event) for event in generation_context.memory_events
            ],
        }
        return result

    @router.get("/projects/{project_id}/generations")
    def list_generations(project_id: int, limit: int = 20) -> list[dict[str, Any]]:
        services.projects.require_project(project_id)
        return [
            generation_payload(record)
            for record in services.generations.list_for_project(project_id, limit=limit)
        ]

    @router.get("/generations/{generation_id}")
    def get_generation(generation_id: int) -> dict[str, Any]:
        record = services.generations.get(generation_id)
        if record is None:
            raise RecordNotFoundError("That generation no longer exists.")
        return generation_payload(record, include_output=True)

    return router
