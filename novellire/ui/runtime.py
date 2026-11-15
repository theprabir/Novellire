"""Shared Streamlit runtime: settings, database, services, and cached provider.

Streamlit reruns the whole script on every interaction, so everything expensive
is created once per process through ``st.cache_resource``.
"""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from ..config import Settings, load_settings
from ..core.generation import GenerationService
from ..core.projects import ProjectService
from ..core.settings_service import AppSettingsService
from ..llm.base import ModelInfo
from ..llm.ollama import OllamaProvider
from ..logging_setup import configure_logging
from ..storage.database import Database
from ..storage.repositories import (
    AppSettingsRepository,
    GenerationRepository,
    ProjectRepository,
)


@dataclass
class AppContext:
    """Everything a page needs; assembled once per process."""

    settings: Settings
    database: Database
    provider: OllamaProvider
    projects: ProjectService
    generation: GenerationService
    app_settings: AppSettingsService
    generations: GenerationRepository


@st.cache_resource(show_spinner=False)
def get_context() -> AppContext:
    """Build the application context and apply database migrations."""
    settings = load_settings()
    configure_logging(settings.log_level)

    database = Database(settings.database_path)
    database.initialize()

    provider = OllamaProvider(
        base_url=settings.ollama.base_url,
        request_timeout=settings.ollama.request_timeout_seconds,
        connect_timeout=settings.ollama.connect_timeout_seconds,
        keep_alive=settings.ollama.keep_alive,
    )

    project_repository = ProjectRepository(database)
    generation_repository = GenerationRepository(database)
    app_settings_repository = AppSettingsRepository(database)

    return AppContext(
        settings=settings,
        database=database,
        provider=provider,
        projects=ProjectService(project_repository),
        generation=GenerationService(
            provider, project_repository, generation_repository
        ),
        app_settings=AppSettingsService(
            app_settings_repository, settings.generation
        ),
        generations=generation_repository,
    )


@st.cache_data(ttl=10, show_spinner=False)
def ollama_available() -> bool:
    """Cheap connectivity probe, cached to avoid a request on every rerun."""
    return get_context().provider.is_available()


@st.cache_data(ttl=20, show_spinner=False)
def available_models() -> list[ModelInfo]:
    """Installed models, cached briefly so the UI stays responsive."""
    return get_context().provider.list_models()


def refresh_provider_state() -> None:
    """Drop cached Ollama state so the next render re-probes the server."""
    ollama_available.clear()
    available_models.clear()
