"""OpenAI-compatible cloud provider, disabled unless explicitly configured.

Many hosted services expose the same ``/chat/completions`` shape (OpenAI,
OpenRouter, Groq, Together, and local servers such as LM Studio). This provider
implements only that shared surface, keeps the key in memory, and never logs a
prompt or a completion. It is selected at startup only when ``[cloud].enabled``
is true; Novellire does not fall back to it silently.

Nothing here decides when cloud inference is appropriate. Every caller already
uses the ``LLMProvider`` protocol, so choosing this provider is the only switch.
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
    MissingCloudKeyError,
)
from ..logging_setup import get_logger
from .base import GenerationChunk, GenerationRequest, GenerationResult, ModelInfo

logger = get_logger("llm.openai_compatible")

_ERROR_BODY_LIMIT = 300


class OpenAICompatibleProvider:
    """Hosted inference over an OpenAI-compatible HTTP API."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        request_timeout: float = 120.0,
        connect_timeout: float = 10.0,
        session: requests.Session | None = None,
    ) -> None:
        cleaned_key = (api_key or "").strip()
        if not cleaned_key:
            raise MissingCloudKeyError(
                "Cloud inference is enabled but no API key was found. Set the "
                "environment variable named by cloud.api_key_env in config.toml."
            )
        self._base_url = base_url.rstrip("/")
        self._api_key = cleaned_key
        self._timeout = (float(connect_timeout), float(request_timeout))
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
        """Return True when the API answers an authenticated model list."""
        try:
            self._get_json("/models", timeout=(self._timeout[0], 10.0))
        except Exception:  # noqa: BLE001 - availability must never raise
            return False
        return True

    def list_models(self) -> list[ModelInfo]:
        payload = self._get_json("/models", timeout=(self._timeout[0], 20.0))
        raw_models = payload.get("data")
        if not isinstance(raw_models, list):
            raise LLMResponseError(
                "The cloud API returned an unexpected model list. Check that "
                "cloud.base_url points at an OpenAI-compatible API root."
            )
        models: list[ModelInfo] = []
        for entry in raw_models:
            if not isinstance(entry, dict):
                continue
            name = entry.get("id")
            if isinstance(name, str) and name.strip():
                models.append(ModelInfo(name=name.strip()))
        return sorted(models, key=lambda model: model.name)

    # -- generation --------------------------------------------------------

    def generate(self, request: GenerationRequest) -> GenerationResult:
        payload = self._payload(request, stream=False)
        started = time.perf_counter()
        response = self._post("/chat/completions", payload)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        data = self._response_json(response, model=request.model)
        text, finish_reason = self._message_text(data)
        if not text.strip():
            raise LLMResponseError(
                "The cloud API returned an empty response. Try a different model "
                "or raise the maximum output tokens."
            )
        usage = data.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        logger.info(
            "Cloud generation ok: model=%s chars=%d finish=%s",
            request.model,
            len(text),
            finish_reason or "unknown",
        )
        return GenerationResult(
            text=text,
            model=_optional_str(data.get("model")) or request.model,
            duration_ms=elapsed_ms,
            truncated=finish_reason == "length",
            prompt_tokens=_optional_int(usage.get("prompt_tokens")),
            output_tokens=_optional_int(usage.get("completion_tokens")),
        )

    def generate_stream(
        self, request: GenerationRequest
    ) -> Iterator[GenerationChunk]:
        """Yield server-sent text deltas, then one final chunk."""
        payload = self._payload(request, stream=True)
        response = self._post("/chat/completions", payload, stream=True)
        model = request.model
        produced = 0
        finish_reason = ""
        try:
            for raw_line in response.iter_lines():
                if not raw_line:
                    continue
                line = (
                    raw_line.decode("utf-8", "replace")
                    if isinstance(raw_line, bytes)
                    else raw_line
                )
                if not line.startswith("data:"):
                    continue
                body = line[len("data:") :].strip()
                if body == "[DONE]":
                    break
                try:
                    data = json.loads(body)
                except (TypeError, ValueError) as exc:
                    raise LLMResponseError(
                        "The cloud API streamed a line that is not valid JSON."
                    ) from exc
                if not isinstance(data, dict):
                    continue
                error = data.get("error")
                if isinstance(error, dict) and error.get("message"):
                    raise LLMResponseError(
                        f"The cloud API stopped generating: "
                        f"{str(error['message'])[:_ERROR_BODY_LIMIT]}"
                    )
                model = _optional_str(data.get("model")) or model
                choices = data.get("choices")
                for choice in choices if isinstance(choices, list) else []:
                    if not isinstance(choice, dict):
                        continue
                    delta = choice.get("delta")
                    piece = delta.get("content") if isinstance(delta, dict) else None
                    if isinstance(piece, str) and piece:
                        produced += len(piece)
                        yield GenerationChunk(text=piece)
                    reason = choice.get("finish_reason")
                    if isinstance(reason, str) and reason:
                        finish_reason = reason
            if produced == 0:
                raise LLMResponseError(
                    "The cloud API returned an empty response. Try a different "
                    "model or raise the maximum output tokens."
                )
            logger.info(
                "Cloud streaming ok: model=%s chars=%d", model, produced
            )
            yield GenerationChunk(
                model=model, done=True, truncated=finish_reason == "length"
            )
        except requests.Timeout as exc:
            raise LLMTimeoutError(
                "The cloud API stopped responding while streaming. Raise "
                "cloud.request_timeout_seconds in config.toml or request less text."
            ) from exc
        except requests.RequestException as exc:
            raise LLMUnavailableError(self._unavailable_message()) from exc
        finally:
            response.close()

    # -- HTTP helpers ------------------------------------------------------

    def _payload(self, request: GenerationRequest, *, stream: bool) -> dict[str, Any]:
        messages: list[dict[str, str]] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.prompt})
        return {
            "model": request.model,
            "messages": messages,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "max_tokens": request.num_predict,
            "stream": stream,
        }

    def _get_json(self, path: str, *, timeout: tuple[float, float]) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        try:
            response = self._session.get(
                url, headers=self._headers(), timeout=timeout
            )
        except requests.Timeout as exc:
            raise LLMTimeoutError(
                f"The cloud API did not answer within {timeout[1]:.0f}s."
            ) from exc
        except requests.RequestException as exc:
            raise LLMUnavailableError(self._unavailable_message()) from exc
        return self._response_json(response)

    def _post(
        self, path: str, payload: dict[str, Any], *, stream: bool = False
    ) -> requests.Response:
        url = f"{self._base_url}{path}"
        try:
            return self._session.post(
                url,
                json=payload,
                headers=self._headers(),
                timeout=self._timeout,
                stream=stream,
            )
        except requests.Timeout as exc:
            raise LLMTimeoutError(
                f"The cloud API did not finish within "
                f"{self._timeout[1]:.0f}s. Raise cloud.request_timeout_seconds "
                "or request less text."
            ) from exc
        except requests.RequestException as exc:
            raise LLMUnavailableError(self._unavailable_message()) from exc

    def _response_json(
        self, response: requests.Response, *, model: str = ""
    ) -> dict[str, Any]:
        if response.status_code in (401, 403):
            raise LLMResponseError(
                "The cloud API rejected the API key. Check the environment "
                "variable named by cloud.api_key_env."
            )
        if response.status_code == 404:
            name = f" '{model}'" if model else ""
            raise ModelNotFoundError(
                f"The cloud API has no model{name}. Check cloud.model and the "
                "provider's model list."
            )
        if response.status_code != 200:
            raise LLMResponseError(
                f"The cloud API rejected the request (HTTP "
                f"{response.status_code}): {_body_snippet(response)}"
            )
        try:
            data = response.json()
        except (TypeError, ValueError) as exc:
            raise LLMResponseError(
                "The cloud API returned a response that is not valid JSON."
            ) from exc
        if not isinstance(data, dict):
            raise LLMResponseError(
                "The cloud API returned an unexpected JSON structure."
            )
        return data

    def _message_text(self, data: dict[str, Any]) -> tuple[str, str]:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LLMResponseError(
                "The cloud API returned no choices. Check the selected model."
            )
        first = choices[0]
        if not isinstance(first, dict):
            raise LLMResponseError(
                "The cloud API returned an unexpected choice structure."
            )
        message = first.get("message")
        text = message.get("content") if isinstance(message, dict) else None
        if not isinstance(text, str):
            raise LLMResponseError(
                "The cloud API returned no message text. The model may not "
                "support chat completions."
            )
        reason = first.get("finish_reason")
        return text, reason if isinstance(reason, str) else ""

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _unavailable_message(self) -> str:
        return (
            f"Could not reach the cloud API at {self._base_url}. Check the "
            "network connection and cloud.base_url in config.toml."
        )


def _body_snippet(response: requests.Response) -> str:
    text = response.text or ""
    return " ".join(text.split())[:_ERROR_BODY_LIMIT] or "<empty response>"


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _optional_int(value: object) -> int | None:
    return int(value) if isinstance(value, int) else None
