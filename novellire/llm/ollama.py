"""Ollama provider.

Uses the local HTTP API with ``stream: false`` so one request occupies one
connection and one model load. Every failure mode is mapped to a domain error
with an actionable message, and no manuscript text is logged.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from typing import Any

import requests

from ..errors import (
    LLMResponseError,
    LLMTimeoutError,
    LLMUnavailableError,
    ModelNotFoundError,
)
from ..logging_setup import get_logger
from .base import GenerationChunk, GenerationRequest, GenerationResult, ModelInfo

logger = get_logger("llm.ollama")

_MODEL_NOT_FOUND_HINT = "not found"
_ERROR_BODY_LIMIT = 300


class OllamaProvider:
    """Local Ollama inference over HTTP."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        *,
        request_timeout: float = 180.0,
        connect_timeout: float = 5.0,
        keep_alive: str = "5m",
        session: requests.Session | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = (float(connect_timeout), float(request_timeout))
        self._keep_alive = keep_alive
        self._session = session if session is not None else requests.Session()

    @property
    def base_url(self) -> str:
        return self._base_url

    def close(self) -> None:
        close = getattr(self._session, "close", None)
        if callable(close):
            close()

    # -- discovery ---------------------------------------------------------

    def is_available(self) -> bool:
        """Return True when Ollama answers ``/api/tags``."""
        try:
            self._get_json("/api/tags", timeout=(self._timeout[0], 5.0))
        except Exception:  # noqa: BLE001 - availability must never raise
            return False
        return True

    def list_models(self) -> list[ModelInfo]:
        payload = self._get_json("/api/tags", timeout=(self._timeout[0], 15.0))
        raw_models = payload.get("models")
        if not isinstance(raw_models, list):
            raise LLMResponseError(
                "Ollama returned an unexpected model list. Check that the local "
                "Ollama version is current."
            )

        models: list[ModelInfo] = []
        for entry in raw_models:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            details = entry.get("details")
            details = details if isinstance(details, dict) else {}
            size = entry.get("size")
            models.append(
                ModelInfo(
                    name=name.strip(),
                    size_bytes=int(size) if isinstance(size, int) else None,
                    parameter_size=_optional_str(details.get("parameter_size")),
                    quantization=_optional_str(details.get("quantization_level")),
                    family=_optional_str(details.get("family")),
                )
            )
        return sorted(models, key=lambda model: model.name)

    # -- generation --------------------------------------------------------

    def generate(self, request: GenerationRequest) -> GenerationResult:
        payload = self._payload(request)
        started = time.perf_counter()
        response = self._post("/api/generate", payload)
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        if response.status_code == 404:
            raise ModelNotFoundError(self._model_error_message(response, request.model))
        if response.status_code != 200:
            raise LLMResponseError(
                f"Ollama rejected the request (HTTP {response.status_code}): "
                f"{self._body_snippet(response)}"
            )

        data = self._parse_json(response)
        text = data.get("response")
        if not isinstance(text, str):
            raise LLMResponseError(
                "Ollama returned no text field. The model may not support generation."
            )
        if not text.strip():
            raise LLMResponseError(
                "Ollama returned an empty response. Try reducing the context window "
                "or increasing the maximum output tokens."
            )

        total_duration = data.get("total_duration")
        duration_ms = int(total_duration / 1_000_000) if isinstance(total_duration, int) else elapsed_ms

        logger.info(
            "Ollama generation ok: model=%s chars=%d duration_ms=%d",
            request.model,
            len(text),
            duration_ms,
        )
        return GenerationResult(
            text=text,
            model=_optional_str(data.get("model")) or request.model,
            duration_ms=duration_ms,
            truncated=data.get("done_reason") == "length",
            prompt_tokens=_optional_int(data.get("prompt_eval_count")),
            output_tokens=_optional_int(data.get("eval_count")),
        )

    def generate_stream(
        self, request: GenerationRequest
    ) -> Iterator[GenerationChunk]:
        """Yield the model's text as it arrives, one Ollama JSON line at a time."""
        payload = self._payload(request)
        payload["stream"] = True
        response = self._post("/api/generate", payload, stream=True)
        if response.status_code == 404:
            raise ModelNotFoundError(self._model_error_message(response, request.model))
        if response.status_code != 200:
            raise LLMResponseError(
                f"Ollama rejected the request (HTTP {response.status_code}): "
                f"{self._body_snippet(response)}"
            )

        model = request.model
        produced = 0
        started = time.perf_counter()
        try:
            for raw_line in response.iter_lines():
                if not raw_line:
                    continue
                data = self._parse_stream_line(raw_line)
                error = data.get("error")
                if isinstance(error, str) and error.strip():
                    raise LLMResponseError(
                        f"Ollama stopped generating: {error.strip()[:_ERROR_BODY_LIMIT]}"
                    )
                piece = data.get("response")
                if isinstance(piece, str) and piece:
                    produced += len(piece)
                    yield GenerationChunk(text=piece)
                name = data.get("model")
                if isinstance(name, str) and name.strip():
                    model = name.strip()
                if data.get("done"):
                    if produced == 0:
                        raise LLMResponseError(
                            "Ollama returned an empty response. Try reducing the "
                            "context window or increasing the maximum output tokens."
                        )
                    truncated = data.get("done_reason") == "length"
                    logger.info(
                        "Ollama streaming ok: model=%s chars=%d duration_ms=%d",
                        model,
                        produced,
                        int((time.perf_counter() - started) * 1000),
                    )
                    yield GenerationChunk(
                        model=model, done=True, truncated=truncated
                    )
        except requests.Timeout as exc:
            raise LLMTimeoutError(
                f"Ollama stopped responding while streaming. Reduce the requested "
                "length, or raise request_timeout_seconds in config.toml."
            ) from exc
        except requests.RequestException as exc:
            raise LLMUnavailableError(self._unavailable_message()) from exc
        finally:
            response.close()

    def _payload(self, request: GenerationRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model,
            "prompt": request.prompt,
            "stream": False,
            "keep_alive": self._keep_alive,
            "options": {
                "temperature": request.temperature,
                "top_p": request.top_p,
                "num_predict": request.num_predict,
                "num_ctx": request.context_window,
            },
        }
        if request.system_prompt:
            payload["system"] = request.system_prompt
        if request.seed is not None:
            payload["options"]["seed"] = request.seed
        if request.stop:
            payload["options"]["stop"] = list(request.stop)
        return payload

    # -- HTTP helpers ------------------------------------------------------

    def _get_json(self, path: str, *, timeout: tuple[float, float]) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        try:
            response = self._session.get(url, timeout=timeout)
        except requests.Timeout as exc:
            raise LLMTimeoutError(
                f"Ollama did not answer within {timeout[1]:.0f}s at {self._base_url}."
            ) from exc
        except requests.ConnectionError as exc:
            raise LLMUnavailableError(self._unavailable_message()) from exc
        except requests.RequestException as exc:
            raise LLMUnavailableError(self._unavailable_message()) from exc

        if response.status_code != 200:
            raise LLMResponseError(
                f"Ollama answered HTTP {response.status_code}: {self._body_snippet(response)}"
            )
        return self._parse_json(response)

    def _post(
        self, path: str, payload: dict[str, Any], *, stream: bool = False
    ) -> requests.Response:
        url = f"{self._base_url}{path}"
        try:
            return self._session.post(
                url, json=payload, timeout=self._timeout, stream=stream
            )
        except requests.Timeout as exc:
            raise LLMTimeoutError(
                f"Ollama did not finish generating within "
                f"{self._timeout[1]:.0f}s. Reduce the requested length, or raise "
                "request_timeout_seconds in config.toml."
            ) from exc
        except requests.ConnectionError as exc:
            raise LLMUnavailableError(self._unavailable_message()) from exc
        except requests.RequestException as exc:
            raise LLMUnavailableError(self._unavailable_message()) from exc

    @staticmethod
    def _parse_stream_line(raw_line: bytes | str) -> dict[str, Any]:
        try:
            data = json.loads(raw_line)
        except (ValueError, json.JSONDecodeError) as exc:
            raise LLMResponseError(
                "Ollama streamed a line that is not valid JSON. Check that the "
                "local Ollama version is current."
            ) from exc
        if not isinstance(data, dict):
            raise LLMResponseError("Ollama streamed an unexpected JSON structure.")
        return data

    def _parse_json(self, response: requests.Response) -> dict[str, Any]:
        try:
            data = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise LLMResponseError(
                f"Ollama returned a response that is not valid JSON: "
                f"{self._body_snippet(response)}"
            ) from exc
        if not isinstance(data, dict):
            raise LLMResponseError("Ollama returned an unexpected JSON structure.")
        return data

    def _unavailable_message(self) -> str:
        return (
            f"Could not reach Ollama at {self._base_url}. Start it with "
            "`ollama serve` and confirm `ollama list` works in a terminal."
        )

    def _model_error_message(self, response: requests.Response, model: str) -> str:
        body = self._body_snippet(response).lower()
        if _MODEL_NOT_FOUND_HINT in body:
            return (
                f"Model '{model}' is not installed in Ollama. "
                f"Install it with `ollama pull {model}`, then refresh the model list."
            )
        return f"Ollama returned HTTP 404 for this request: {self._body_snippet(response)}"

    @staticmethod
    def _body_snippet(response: requests.Response) -> str:
        text = response.text or ""
        text = " ".join(text.split())
        return text[:_ERROR_BODY_LIMIT] or "<empty response>"


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _optional_int(value: object) -> int | None:
    return int(value) if isinstance(value, int) else None
