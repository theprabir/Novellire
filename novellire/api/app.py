"""FastAPI application: JSON API plus the static browser client.

The API is a thin transport layer. Validation, prompt construction, storage, and
inference all live in the existing services, so the browser client and the CLI
share exactly the same rules.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
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
from ..core.backup import BackupService
from ..core.chapters import ChapterService
from ..core.character_states import CharacterStateService
from ..core.characters import FIELD_LABELS as CHARACTER_FIELD_LABELS
from ..core.characters import PROFILE_FIELDS, CharacterService
from ..core.context import GenerationContextBuilder
from ..core.documents import ProjectDocumentService, WORKSPACE_DOCUMENTS
from ..core.events import EventExtractionService
from ..core.export import ExportService
from ..core.generation import GenerationService
from ..core.memory import MemoryService
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
from ..logging_setup import configure_logging
from ..storage.database import Database
from ..storage.document_repository import DocumentRepository
from ..storage.event_repository import EventRepository
from ..storage.search_repository import SearchRepository
from ..storage.relationship_repository import RelationshipRepository
from ..storage.state_repository import CharacterStateRepository
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


def build_services(
    settings: Settings, database: Database, provider: LLMProvider
) -> ApiServices:
    project_repository = ProjectRepository(database)
    generation_repository = GenerationRepository(database)
    character_repository = CharacterRepository(database)
    chapter_repository = ChapterRepository(database)
    bible_repository = StoryBibleRepository(database)
    event_repository = EventRepository(database)
    relationship_repository = RelationshipRepository(database)
    state_repository = CharacterStateRepository(database)
    chapter_service = ChapterService(
        chapter_repository, project_repository, character_repository
    )
    document_service = ProjectDocumentService(
        DocumentRepository(database), project_repository
    )

    return ApiServices(
        settings=settings,
        database=database,
        provider=provider,
        projects=ProjectService(project_repository),
        projects_repository=project_repository,
        generation=GenerationService(
            provider, project_repository, generation_repository
        ),
        app_settings=AppSettingsService(
            AppSettingsRepository(database), settings.generation
        ),
        story_bible=StoryBibleService(bible_repository, project_repository),
        characters=CharacterService(character_repository, project_repository),
        chapters=chapter_service,
        scenes=SceneService(SceneRepository(database), chapter_repository),
        documents=document_service,
        export=ExportService(
            project_repository, chapter_service, document_service
        ),
        summaries=ChapterSummaryService(
            provider, project_repository, chapter_service
        ),
        memory=MemoryService(SearchRepository(database), project_repository),
        events=EventExtractionService(
            provider,
            project_repository,
            chapter_service,
            event_repository,
            character_repository,
        ),
        event_repository=event_repository,
        relationships=RelationshipService(
            project_repository,
            character_repository,
            event_repository,
            relationship_repository,
        ),
        character_states=CharacterStateService(
            project_repository,
            character_repository,
            chapter_repository,
            state_repository,
        ),
        backup=BackupService(database),
        context=GenerationContextBuilder(
            document_service,
            bible_repository,
            character_repository,
            chapter_repository,
            SearchRepository(database),
            event_repository,
            relationship_repository,
            state_repository,
        ),
        style_guide=StyleGuideService(
            provider, project_repository, chapter_service, document_service
        ),
        generations=generation_repository,
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

    app = FastAPI(
        title="Novellire",
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
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
            part=payload.part,
            summary=payload.summary,
            objectives=payload.objectives,
            viewpoint_character_id=payload.viewpoint_character_id,
            target_word_count=payload.target_word_count,
            status=payload.status,
            content=payload.content,
            origin=payload.origin,
        )
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
        return asdict(services.chapters.update_chapter(chapter_id, **kwargs))

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
