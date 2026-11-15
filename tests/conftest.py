"""Shared pytest fixtures and a deterministic in-memory LLM provider."""

from __future__ import annotations

from pathlib import Path

import pytest

from novellire.config import GenerationDefaults
from novellire.core.generation import GenerationService
from novellire.core.projects import ProjectService
from novellire.core.settings_service import AppSettingsService, GenerationSettings
from novellire.llm.base import GenerationRequest, GenerationResult, ModelInfo
from novellire.storage.database import Database
from novellire.storage.repositories import (
    AppSettingsRepository,
    GenerationRepository,
    ProjectRepository,
    Project,
)


class FakeProvider:
    """Provider stub: records requests instead of contacting Ollama."""

    def __init__(
        self,
        *,
        result: GenerationResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.requests: list[GenerationRequest] = []

    def is_available(self) -> bool:
        return self.error is None

    def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(name="fake-model", parameter_size="1B")]

    def generate(self, request: GenerationRequest) -> GenerationResult:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        if self.result is not None:
            return self.result
        return GenerationResult(
            text=" ".join(["word"] * 120),
            model=request.model,
            duration_ms=42,
            prompt_tokens=10,
            output_tokens=120,
        )


@pytest.fixture()
def database(tmp_path: Path) -> Database:
    db = Database(tmp_path / "novellire-test.db")
    db.initialize()
    return db


@pytest.fixture()
def project_repository(database: Database) -> ProjectRepository:
    return ProjectRepository(database)


@pytest.fixture()
def generation_repository(database: Database) -> GenerationRepository:
    return GenerationRepository(database)


@pytest.fixture()
def project_service(project_repository: ProjectRepository) -> ProjectService:
    return ProjectService(project_repository)


@pytest.fixture()
def app_settings_service(database: Database) -> AppSettingsService:
    return AppSettingsService(
        AppSettingsRepository(database),
        GenerationDefaults(model="fake-model"),
    )


@pytest.fixture()
def sample_project(project_service: ProjectService) -> Project:
    return project_service.create_project(
        name="Ashfall",
        description="A city beneath a dying star.",
        genre="Science fiction",
        narrative_style="Close third person, past tense",
        target_word_count=90_000,
    )


@pytest.fixture()
def fake_provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture()
def fake_provider_factory():
    def make(**kwargs: object) -> FakeProvider:
        return FakeProvider(**kwargs)  # type: ignore[arg-type]

    return make


@pytest.fixture()
def generation_service(
    fake_provider: FakeProvider,
    project_repository: ProjectRepository,
    generation_repository: GenerationRepository,
) -> GenerationService:
    return GenerationService(fake_provider, project_repository, generation_repository)


@pytest.fixture()
def generation_settings() -> GenerationSettings:
    return GenerationSettings(
        model="fake-model",
        temperature=0.7,
        top_p=0.9,
        num_predict=256,
        context_window=2048,
    )
