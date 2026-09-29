"""Chat-completion transports: the only code that talks to a model API over the network.

`OpenAICompatibleTransport` speaks the OpenAI `/chat/completions` format that Qwen, DeepSeek,
Kimi, GLM, vLLM, Ollama and most managed inference services accept, so switching provider is a
configuration change (docs/PROJECT_SPEC.md §33).

Privacy (spec §70, §94): request and response bodies are never logged or put into errors.
"""

from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.ai.failures import FailureKind, classify_http
from app.ai.structured import ResponseSchema
from app.core.errors import AIUnavailableError


@dataclass(frozen=True)
class ChatMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass(frozen=True)
class ChatCompletion:
    content: str
    # The model id the provider reports having served, which can be more specific than the one
    # requested (a dated snapshot). Stored as the model version (spec §74).
    served_model: str | None
    # True when generation stopped at the token limit, so the content is cut off.
    truncated: bool


class ChatTransport(Protocol):
    def complete(
        self,
        *,
        model: str,
        messages: list[ChatMessage],
        temperature: float,
        max_tokens: int,
        json_mode: bool,
        response_schema: ResponseSchema | None = None,
    ) -> ChatCompletion: ...


class OpenAICompatibleTransport:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float,
        client: httpx.Client | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._url = base_url.rstrip("/") + "/chat/completions"
        # Self-hosted endpoints often need no key; send the header only when one is set.
        self._headers = dict(extra_headers or {})
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"
        self._client = client or httpx.Client(timeout=timeout)

    def __repr__(self) -> str:
        # Never show headers (they carry the key).
        return f"OpenAICompatibleTransport(url={self._url!r})"

    def complete(
        self,
        *,
        model: str,
        messages: list[ChatMessage],
        temperature: float,
        max_tokens: int,
        json_mode: bool,
        response_schema: ResponseSchema | None = None,
    ) -> ChatCompletion:
        body: dict[str, Any] = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": response_schema.name,
                    "schema": response_schema.schema,
                    "strict": response_schema.strict,
                },
            }
        elif json_mode:
            body["response_format"] = {"type": "json_object"}

        response = post_json(self._client, self._url, body, self._headers)
        return _parse_completion(response)


def post_json(
    client: httpx.Client, url: str, body: dict[str, Any], headers: dict[str, str]
) -> httpx.Response:
    """POSTs and turns every failure into an AIUnavailableError with a FailureKind."""
    try:
        response = client.post(url, json=body, headers=headers)
    except httpx.TimeoutException as exc:
        raise AIUnavailableError(
            "The AI provider took too long to answer.",
            details={"reason": "timeout", "failure": FailureKind.TIMEOUT},
        ) from exc
    except httpx.HTTPError as exc:
        raise AIUnavailableError(
            "The AI provider couldn't be reached.",
            details={"reason": "connection", "failure": FailureKind.PROVIDER_UNAVAILABLE},
        ) from exc
    if response.status_code != 200:
        # The body is read only to classify the failure; it never goes into the error.
        failure = classify_http(response.status_code, response.text[:4000])
        raise AIUnavailableError(
            "The AI provider returned an error.",
            details={"reason": "http_status", "status": response.status_code, "failure": failure},
        )
    return response


def _parse_completion(response: httpx.Response) -> ChatCompletion:
    try:
        payload = response.json()
        choice = payload["choices"][0]
        content = choice["message"]["content"]
        if not isinstance(content, str):
            raise TypeError("content is not a string")
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise AIUnavailableError(
            "The AI provider's response wasn't in the expected format.",
            details={"reason": "bad_response", "failure": FailureKind.PROVIDER_UNAVAILABLE},
        ) from exc
    served = payload.get("model")
    return ChatCompletion(
        content=content,
        served_model=served if isinstance(served, str) else None,
        truncated=choice.get("finish_reason") == "length",
    )
