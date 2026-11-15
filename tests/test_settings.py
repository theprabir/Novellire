"""Persisted generation settings and active-project selection."""

from __future__ import annotations

import json

from novellire.core.settings_service import (
    ACTIVE_PROJECT_KEY,
    GENERATION_SETTINGS_KEY,
    AppSettingsService,
    GenerationSettings,
)
from novellire.config import GenerationDefaults
from novellire.storage.repositories import AppSettingsRepository


def test_defaults_come_from_configuration(
    app_settings_service: AppSettingsService,
) -> None:
    settings = app_settings_service.generation_settings()
    assert settings.model == "fake-model"
    assert settings.context_window == 4096


def test_saved_settings_round_trip(app_settings_service: AppSettingsService) -> None:
    app_settings_service.save_generation_settings(
        GenerationSettings(
            model="qwen2.5:1.5b",
            temperature=0.35,
            top_p=0.75,
            num_predict=512,
            context_window=8192,
        )
    )

    reloaded = app_settings_service.generation_settings()
    assert reloaded.model == "qwen2.5:1.5b"
    assert reloaded.temperature == 0.35
    assert reloaded.top_p == 0.75
    assert reloaded.num_predict == 512
    assert reloaded.context_window == 8192


def test_corrupted_json_falls_back_to_defaults(database) -> None:
    repository = AppSettingsRepository(database)
    repository.set(GENERATION_SETTINGS_KEY, "{not json")
    service = AppSettingsService(repository, GenerationDefaults(model="fallback"))

    settings = service.generation_settings()

    assert settings.model == "fallback"
    assert settings.temperature == 0.8


def test_out_of_range_stored_values_fall_back(database) -> None:
    repository = AppSettingsRepository(database)
    repository.set(
        GENERATION_SETTINGS_KEY,
        json.dumps({"model": "x", "temperature": 9.0}),
    )
    service = AppSettingsService(repository, GenerationDefaults(model="fallback"))

    assert service.generation_settings().model == "fallback"


def test_active_project_selection_round_trip(
    app_settings_service: AppSettingsService, database
) -> None:
    assert app_settings_service.active_project_id() is None

    app_settings_service.set_active_project_id(7)
    assert app_settings_service.active_project_id() == 7

    app_settings_service.set_active_project_id(None)
    assert app_settings_service.active_project_id() is None
    assert AppSettingsRepository(database).get(ACTIVE_PROJECT_KEY) is None


def test_non_numeric_active_project_is_ignored(database) -> None:
    repository = AppSettingsRepository(database)
    repository.set(ACTIVE_PROJECT_KEY, "seven")
    service = AppSettingsService(repository)

    assert service.active_project_id() is None
