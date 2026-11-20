"""Application configuration: defaults, TOML loading, and environment overrides.

Configuration is intentionally small for Phase 1: paths, Ollama connection
settings, and generation defaults. Per-project and per-model selections are
stored in the database instead (see ``novellire.core.settings_service``).
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .errors import ConfigurationError

PACKAGE_DIR = Path(__file__).resolve().parent
APP_ROOT = PACKAGE_DIR.parent
DEFAULT_CONFIG_FILE = APP_ROOT / "config.toml"


class OllamaSettings(BaseModel):
    """Connection settings for a local Ollama server."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    base_url: str = "http://localhost:11434"
    request_timeout_seconds: float = Field(default=180.0, gt=0)
    connect_timeout_seconds: float = Field(default=5.0, gt=0)
    keep_alive: str = "5m"


class CloudSettings(BaseModel):
    """Opt-in OpenAI-compatible cloud inference.

    Disabled by default, and no key is stored here: ``api_key_env`` names the
    environment variable that holds it, so a configuration file can be shared
    without exposing the secret. Enabling this means prompt text and the
    retrieved context for each request leave this machine.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    base_url: str = "https://api.openai.com/v1"
    api_key_env: str = "NOVELLIRE_CLOUD_API_KEY"
    model: str = ""
    request_timeout_seconds: float = Field(default=120.0, gt=0)
    connect_timeout_seconds: float = Field(default=10.0, gt=0)

    @field_validator("base_url")
    @classmethod
    def _require_http_url(cls, value: str) -> str:
        cleaned = value.strip().rstrip("/")
        if not cleaned.startswith(("http://", "https://")):
            raise ValueError("cloud.base_url must start with http:// or https://")
        return cleaned

    @field_validator("api_key_env")
    @classmethod
    def _require_env_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("cloud.api_key_env must name an environment variable")
        return cleaned

    def api_key(self) -> str:
        """Read the key from the named environment variable, never from config."""
        return os.environ.get(self.api_key_env, "").strip()


class GenerationDefaults(BaseModel):
    """Default generation parameters, all overridable in the UI.

    The defaults are deliberately conservative: a small context window and a
    bounded output length keep memory use reasonable on an 8 GB machine.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str = ""
    temperature: float = Field(default=0.8, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, gt=0.0, le=1.0)
    num_predict: int = Field(default=700, ge=32, le=8192)
    context_window: int = Field(default=4096, ge=512, le=32768)


class AnalysisSettings(BaseModel):
    """Automatic memory analysis controls."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    auto_run: bool = True


class Settings(BaseModel):
    """Validated application settings."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    data_dir: Path = APP_ROOT / "data"
    log_level: str = "INFO"
    ollama: OllamaSettings = OllamaSettings()
    cloud: CloudSettings = CloudSettings()
    generation: GenerationDefaults = GenerationDefaults()
    analysis: AnalysisSettings = AnalysisSettings()

    @field_validator("data_dir")
    @classmethod
    def _resolve_data_dir(cls, value: Path) -> Path:
        path = value.expanduser()
        return path if path.is_absolute() else (APP_ROOT / path).resolve()

    @field_validator("log_level")
    @classmethod
    def _normalize_log_level(cls, value: str) -> str:
        level = value.strip().upper()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if level not in allowed:
            raise ValueError(f"log_level must be one of {sorted(allowed)}")
        return level

    @property
    def database_path(self) -> Path:
        return self.data_dir / "novellire.db"


def _merge_override(
    raw: dict[str, object], section_name: str, **values: object
) -> dict[str, object]:
    existing = raw.get(section_name)
    section = dict(existing) if isinstance(existing, dict) else {}
    section.update(values)
    return section


def _merge_ollama_override(raw: dict[str, object], base_url: str) -> dict[str, object]:
    return _merge_override(raw, "ollama", base_url=base_url)


def load_settings(config_path: Path | None = None) -> Settings:
    """Load settings from TOML, applying environment overrides.

    A missing configuration file is not an error: defaults are used.
    """
    configured = os.environ.get("NOVELLIRE_CONFIG")
    path = config_path or (Path(configured) if configured else DEFAULT_CONFIG_FILE)

    raw: dict[str, object] = {}
    if path.is_file():
        try:
            with path.open("rb") as handle:
                raw = tomllib.load(handle)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ConfigurationError(
                f"Could not read the configuration file at {path}: {exc}"
            ) from exc

    data_dir_override = os.environ.get("NOVELLIRE_DATA_DIR")
    if data_dir_override:
        raw["data_dir"] = data_dir_override

    ollama_url_override = os.environ.get("NOVELLIRE_OLLAMA_URL")
    if ollama_url_override:
        raw["ollama"] = _merge_ollama_override(raw, ollama_url_override)

    cloud_overrides: dict[str, object] = {}
    cloud_url_override = os.environ.get("NOVELLIRE_CLOUD_URL")
    if cloud_url_override:
        cloud_overrides["base_url"] = cloud_url_override
    cloud_model_override = os.environ.get("NOVELLIRE_CLOUD_MODEL")
    if cloud_model_override:
        cloud_overrides["model"] = cloud_model_override
    cloud_enabled_override = os.environ.get("NOVELLIRE_CLOUD_ENABLED")
    if cloud_enabled_override:
        cloud_overrides["enabled"] = cloud_enabled_override.strip().casefold() in {
            "1",
            "true",
            "yes",
            "on",
        }
    if cloud_overrides:
        raw["cloud"] = _merge_override(raw, "cloud", **cloud_overrides)

    try:
        return Settings.model_validate(raw)
    except ValidationError as exc:
        raise ConfigurationError(
            f"Invalid configuration in {path}: {exc}"
        ) from exc
