"""Opt-in cloud provider, provider selection, and the reported connection status."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import requests
from fastapi.testclient import TestClient

from novellire.api.app import create_app
from novellire.config import (
    AnalysisSettings,
    CloudSettings,
    GenerationDefaults,
    Settings,
    load_settings,
)
from novellire.errors import (
    LLMResponseError,
    MissingCloudKeyError,
    ModelNotFoundError,
)
from novellire.llm.base import GenerationRequest
from novellire.llm.factory import build_provider
from novellire.llm.ollama import OllamaProvider
from novellire.llm.openai_compatible import OpenAICompatibleProvider
from novellire.storage.database import Database


class StubResponse:
    def __init__(
        self,
        status_code: int = 200,
        payload: object = None,
        lines: list[object] | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self._lines = lines or []
        self.text = json.dumps(payload) if payload is not None else ""
        self.closed = False

    def json(self):
        if self._payload is None:
            raise ValueError("Response is not JSON")
        return self._payload

    def iter_lines(self):
        for line in self._lines:
            yield line if isinstance(line, bytes) else str(line).encode("utf-8")

    def close(self) -> None:
        self.closed = True


class StubSession:
    def __init__(self, *, get: object = None, post: object = None) -> None:
        self._get_response = get
        self._post_response = post
        self.calls: list[tuple[str, str, dict]] = []

    def get(self, url: str, **kwargs: object) -> StubResponse:
        self.calls.append(("GET", url, kwargs))
        return _resolve(self._get_response)

    def post(self, url: str, **kwargs: object) -> StubResponse:
        self.calls.append(("POST", url, kwargs))
        return _resolve(self._post_response)


def _resolve(value: object) -> StubResponse:
    if isinstance(value, BaseException):
        raise value
    if value is None:
        raise requests.ConnectionError("No stub response configured")
    return value  # type: ignore[return-value]


def build_cloud(**stubs: object) -> tuple[OpenAICompatibleProvider, StubSession]:
    session = StubSession(**stubs)
    provider = OpenAICompatibleProvider(
        base_url="https://cloud.example/v1",
        api_key="test-key",
        session=session,
    )
    return provider, session


def build_request(**overrides: object) -> GenerationRequest:
    values: dict[str, object] = {
        "prompt": "Write the scene.",
        "model": "cloud-model",
        "system_prompt": "Be concise.",
        "temperature": 0.5,
        "top_p": 0.8,
        "num_predict": 128,
    }
    values.update(overrides)
    return GenerationRequest(**values)  # type: ignore[arg-type]


def test_generate_uses_openai_chat_shape_and_reports_usage() -> None:
    provider, session = build_cloud(
        post=StubResponse(
            200,
            {
                "model": "cloud-model-2026",
                "choices": [
                    {
                        "message": {"content": "The tide turned."},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 11, "completion_tokens": 4},
            },
        )
    )

    result = provider.generate(build_request())

    assert result.text == "The tide turned."
    assert result.model == "cloud-model-2026"
    assert result.prompt_tokens == 11
    assert result.output_tokens == 4
    assert result.truncated is False
    method, url, kwargs = session.calls[0]
    assert (method, url) == ("POST", "https://cloud.example/v1/chat/completions")
    assert kwargs["headers"]["Authorization"] == "Bearer test-key"
    assert kwargs["timeout"] == (10.0, 120.0)
    payload = kwargs["json"]
    assert payload["model"] == "cloud-model"
    assert payload["max_tokens"] == 128
    assert payload["stream"] is False
    assert payload["messages"] == [
        {"role": "system", "content": "Be concise."},
        {"role": "user", "content": "Write the scene."},
    ]


def test_auth_model_and_empty_responses_are_reported_clearly() -> None:
    provider, _ = build_cloud(
        post=StubResponse(401, {"error": {"message": "bad key"}})
    )
    with pytest.raises(LLMResponseError, match="rejected the API key"):
        provider.generate(build_request())

    provider, _ = build_cloud(post=StubResponse(404, {"error": "missing"}))
    with pytest.raises(ModelNotFoundError, match="cloud-model"):
        provider.generate(build_request())

    provider, _ = build_cloud(
        post=StubResponse(200, {"choices": [{"message": {"content": ""}}]})
    )
    with pytest.raises(LLMResponseError, match="empty response"):
        provider.generate(build_request())


def test_model_discovery_and_availability_use_the_authenticated_list() -> None:
    provider, session = build_cloud(
        get=StubResponse(
            200,
            {
                "data": [
                    {"id": "zeta-model"},
                    {"id": "alpha-model"},
                    {"missing": "id"},
                ]
            },
        )
    )

    assert provider.is_available() is True
    assert [model.name for model in provider.list_models()] == [
        "alpha-model",
        "zeta-model",
    ]
    assert session.calls[0][2]["headers"]["Authorization"] == "Bearer test-key"

    offline, _ = build_cloud(get=requests.ConnectionError("offline"))
    assert offline.is_available() is False


def test_streaming_reads_server_sent_deltas() -> None:
    lines = [
        b'data: {"model": "cloud-model", "choices": [{"delta": {"content": "The "}}]}',
        b'data: {"choices": [{"delta": {"content": "tide."}, "finish_reason": "stop"}]}',
        b"data: [DONE]",
    ]
    response = StubResponse(200, {}, lines=lines)
    provider, _ = build_cloud(post=response)

    chunks = list(provider.generate_stream(build_request()))

    assert "".join(chunk.text for chunk in chunks) == "The tide."
    assert chunks[-1].done is True
    assert chunks[-1].model == "cloud-model"
    assert response.closed is True


def test_provider_selection_is_explicit_and_requires_a_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    local = build_provider(Settings(data_dir=tmp_path, generation=GenerationDefaults()))
    assert isinstance(local, OllamaProvider)

    monkeypatch.setenv("NOVELLIRE_CLOUD_API_KEY", "secret")
    cloud = build_provider(
        Settings(
            data_dir=tmp_path,
            cloud=CloudSettings(enabled=True, model="cloud-model"),
        )
    )
    assert isinstance(cloud, OpenAICompatibleProvider)

    monkeypatch.delenv("NOVELLIRE_CLOUD_API_KEY")
    with pytest.raises(MissingCloudKeyError, match="NOVELLIRE_CLOUD_API_KEY"):
        build_provider(
            Settings(
                data_dir=tmp_path,
                cloud=CloudSettings(enabled=True, model="cloud-model"),
            )
        )


def test_cloud_environment_overrides_load_without_a_config_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NOVELLIRE_CLOUD_ENABLED", "true")
    monkeypatch.setenv("NOVELLIRE_CLOUD_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("NOVELLIRE_CLOUD_MODEL", "some/model")

    settings = load_settings(tmp_path / "missing.toml")

    assert settings.cloud.enabled is True
    assert settings.cloud.base_url == "https://openrouter.ai/api/v1"
    assert settings.cloud.model == "some/model"
    assert settings.cloud.api_key_env == "NOVELLIRE_CLOUD_API_KEY"


def test_settings_and_status_report_the_active_provider(
    tmp_path: Path, fake_provider
) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        generation=GenerationDefaults(model="fake-model"),
        analysis=AnalysisSettings(auto_run=False),
        cloud=CloudSettings(enabled=True, model="cloud-model"),
    )
    app = create_app(
        settings=settings,
        database=Database(settings.database_path),
        provider=fake_provider,
    )
    with TestClient(app) as client:
        payload = client.get("/api/settings").json()
        info = payload["provider"]
        status = client.get("/api/providers/status").json()
        legacy = client.get("/api/ollama/status").json()

    assert payload["generation"]["model"] == "cloud-model"

    assert info["kind"] == "cloud"
    assert info["label"] == "Cloud API"
    assert info["base_url"] == "https://api.openai.com/v1"
    assert info["cloud_enabled"] is True
    assert "sent to this API" in info["privacy"]
    assert status["kind"] == "cloud"
    assert status["available"] is True
    assert [model["name"] for model in status["models"]] == ["fake-model"]
    assert legacy["kind"] == "cloud"


def test_local_mode_keeps_the_loopback_provider_reported(
    tmp_path: Path, fake_provider
) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        generation=GenerationDefaults(model="fake-model"),
        analysis=AnalysisSettings(auto_run=False),
    )
    app = create_app(
        settings=settings,
        database=Database(settings.database_path),
        provider=fake_provider,
    )
    with TestClient(app) as client:
        info = client.get("/api/settings").json()["provider"]

    assert info["kind"] == "ollama"
    assert info["base_url"] == "http://localhost:11434"
    assert info["privacy"] == "No project content leaves this machine."
