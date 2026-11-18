"""Ollama provider behaviour with a stubbed HTTP session (no server needed)."""

from __future__ import annotations

import json

import pytest
import requests

from novellire.errors import (
    LLMResponseError,
    LLMTimeoutError,
    LLMUnavailableError,
    ModelNotFoundError,
)
from novellire.llm.base import GenerationRequest
from novellire.llm.ollama import OllamaProvider


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
            if isinstance(line, bytes):
                yield line
            elif isinstance(line, str):
                yield line.encode("utf-8")
            else:
                yield json.dumps(line).encode("utf-8")

    def close(self) -> None:
        self.closed = True


class StubSession:
    """Minimal requests.Session stand-in."""

    def __init__(self, *, get: object = None, post: object = None) -> None:
        self._get_response = get
        self._post_response = post
        self.calls: list[tuple[str, str, dict]] = []

    def get(self, url: str, **kwargs: object) -> StubResponse:
        self.calls.append(("GET", url, kwargs))
        return self._resolve(self._get_response)

    def post(self, url: str, **kwargs: object) -> StubResponse:
        self.calls.append(("POST", url, kwargs))
        return self._resolve(self._post_response)

    @staticmethod
    def _resolve(value: object) -> StubResponse:
        if isinstance(value, BaseException):
            raise value
        if value is None:
            raise requests.ConnectionError("No stub response configured")
        return value  # type: ignore[return-value]


def build_provider(**stubs: object) -> tuple[OllamaProvider, StubSession]:
    session = StubSession(**stubs)
    return OllamaProvider(session=session, base_url="http://localhost:11434"), session


def build_request(**overrides: object) -> GenerationRequest:
    values: dict[str, object] = {
        "prompt": "Write the scene.",
        "model": "qwen2.5:1.5b",
        "system_prompt": "Be concise.",
        "temperature": 0.5,
        "top_p": 0.8,
        "num_predict": 128,
        "context_window": 2048,
    }
    values.update(overrides)
    return GenerationRequest(**values)  # type: ignore[arg-type]


def test_list_models_parses_details_and_sorts() -> None:
    payload = {
        "models": [
            {
                "name": "qwen2.5:1.5b",
                "size": 986_000_000,
                "details": {
                    "parameter_size": "1.5B",
                    "quantization_level": "Q4_K_M",
                    "family": "qwen2",
                },
            },
            {"name": "llama3.2:1b", "size": 1_300_000_000, "details": {}},
            {"size": 1},
            "not-a-model",
        ]
    }
    provider, session = build_provider(get=StubResponse(200, payload))

    models = provider.list_models()

    assert [model.name for model in models] == ["llama3.2:1b", "qwen2.5:1.5b"]
    qwen = models[1]
    assert qwen.size_bytes == 986_000_000
    assert qwen.parameter_size == "1.5B"
    assert qwen.quantization == "Q4_K_M"
    assert qwen.family == "qwen2"
    assert models[0].parameter_size is None
    assert session.calls[0][1] == "http://localhost:11434/api/tags"


def test_list_models_rejects_unexpected_payload() -> None:
    provider, _ = build_provider(get=StubResponse(200, {"models": "nope"}))
    with pytest.raises(LLMResponseError):
        provider.list_models()


def test_is_available_true_when_server_responds() -> None:
    provider, _ = build_provider(get=StubResponse(200, {"models": []}))
    assert provider.is_available() is True


def test_is_available_false_when_server_is_down() -> None:
    provider, _ = build_provider(get=requests.ConnectionError("refused"))
    assert provider.is_available() is False


def test_generate_sends_expected_payload() -> None:
    payload = {
        "response": "The vault door opened.",
        "model": "qwen2.5:1.5b",
        "done_reason": "stop",
        "total_duration": 1_500_000_000,
        "prompt_eval_count": 12,
        "eval_count": 34,
    }
    provider, session = build_provider(post=StubResponse(200, payload))

    result = provider.generate(build_request())

    assert result.text == "The vault door opened."
    assert result.model == "qwen2.5:1.5b"
    assert result.duration_ms == 1500
    assert result.truncated is False
    assert result.prompt_tokens == 12
    assert result.output_tokens == 34

    method, url, kwargs = session.calls[0]
    assert method == "POST"
    assert url == "http://localhost:11434/api/generate"
    body = kwargs["json"]
    assert body["stream"] is False
    assert body["system"] == "Be concise."
    assert body["keep_alive"] == "5m"
    assert body["options"] == {
        "temperature": 0.5,
        "top_p": 0.8,
        "num_predict": 128,
        "num_ctx": 2048,
    }
    assert kwargs["timeout"] == (5.0, 180.0)


def test_generate_marks_truncated_output() -> None:
    payload = {"response": "An unfinished sent", "done_reason": "length"}
    provider, _ = build_provider(post=StubResponse(200, payload))

    result = provider.generate(build_request())

    assert result.truncated is True


def test_generate_rejects_empty_response() -> None:
    provider, _ = build_provider(post=StubResponse(200, {"response": "   "}))
    with pytest.raises(LLMResponseError, match="empty response"):
        provider.generate(build_request())


def test_generate_rejects_malformed_json() -> None:
    provider, _ = build_provider(post=StubResponse(200, None))
    with pytest.raises(LLMResponseError):
        provider.generate(build_request())


def test_generate_reports_missing_model() -> None:
    payload = {"error": 'model "qwen2.5:1.5b" not found, try pulling it first'}
    provider, _ = build_provider(post=StubResponse(404, payload))

    with pytest.raises(ModelNotFoundError, match="ollama pull"):
        provider.generate(build_request())


def test_generate_reports_http_failure() -> None:
    provider, _ = build_provider(post=StubResponse(500, {"error": "out of memory"}))
    with pytest.raises(LLMResponseError, match="500"):
        provider.generate(build_request())


def test_generate_reports_connection_failure() -> None:
    provider, _ = build_provider(post=requests.ConnectionError("refused"))
    with pytest.raises(LLMUnavailableError, match="ollama serve"):
        provider.generate(build_request())


def test_generate_reports_timeout() -> None:
    provider, _ = build_provider(post=requests.Timeout("too slow"))
    with pytest.raises(LLMTimeoutError):
        provider.generate(build_request())


def test_provider_exposes_base_url() -> None:
    provider, _ = build_provider()
    assert provider.base_url == "http://localhost:11434"


def test_generate_stream_yields_text_and_final_metadata() -> None:
    lines = [
        {"model": "qwen2.5:1.5b", "response": "The vault ", "done": False},
        {"model": "qwen2.5:1.5b", "response": "door opened.", "done": False},
        {
            "model": "qwen2.5:1.5b",
            "response": "",
            "done": True,
            "done_reason": "stop",
        },
    ]
    provider, session = build_provider(post=StubResponse(200, lines=lines))

    chunks = list(provider.generate_stream(build_request()))

    assert "".join(chunk.text for chunk in chunks) == "The vault door opened."
    final = chunks[-1]
    assert final.done is True
    assert final.model == "qwen2.5:1.5b"
    assert final.truncated is False
    _, _, kwargs = session.calls[0]
    assert kwargs["json"]["stream"] is True
    assert kwargs["stream"] is True
    assert kwargs["timeout"] == (5.0, 180.0)


def test_generate_stream_marks_truncated_output() -> None:
    lines = [
        {"response": "An unfinished sent", "done": False},
        {"response": "", "done": True, "done_reason": "length"},
    ]
    provider, _ = build_provider(post=StubResponse(200, lines=lines))

    chunks = list(provider.generate_stream(build_request()))

    assert chunks[-1].truncated is True


def test_generate_stream_rejects_an_empty_stream() -> None:
    provider, _ = build_provider(
        post=StubResponse(200, lines=[{"done": True, "done_reason": "stop"}])
    )
    with pytest.raises(LLMResponseError, match="empty response"):
        list(provider.generate_stream(build_request()))


def test_generate_stream_rejects_a_malformed_line() -> None:
    provider, _ = build_provider(post=StubResponse(200, lines=[b"{not json"]))
    with pytest.raises(LLMResponseError, match="not valid JSON"):
        list(provider.generate_stream(build_request()))


def test_generate_stream_reports_a_streamed_model_error() -> None:
    provider, _ = build_provider(
        post=StubResponse(200, lines=[{"error": "out of memory", "done": True}])
    )
    with pytest.raises(LLMResponseError, match="out of memory"):
        list(provider.generate_stream(build_request()))


def test_generate_stream_reports_missing_model() -> None:
    payload = {"error": 'model "qwen2.5:1.5b" not found, try pulling it first'}
    provider, _ = build_provider(post=StubResponse(404, payload))

    with pytest.raises(ModelNotFoundError, match="ollama pull"):
        list(provider.generate_stream(build_request()))
