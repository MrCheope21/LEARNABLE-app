"""Cloudflare Workers AI transport (docs/FREE_AI_ROUTING.md §3).

Workers AI's REST endpoint is not the OpenAI Chat Completions shape, so this small adapter
implements `ChatTransport` for it; everything above (prompts, validation, retries, routing) is
shared. Endpoint: POST {base}/accounts/{account_id}/ai/run/{model}.

A 429 for the exhausted daily free allocation becomes QUOTA_EXHAUSTED and a 403 for a model that
needs Workers Paid becomes MODEL_NOT_FREE (app/ai/failures.py), so routing can move on and never
retry a paid-only model under FREE_ONLY.
"""

import json
from typing import Any

import httpx

from app.ai.failures import FailureKind
from app.ai.structured import ResponseSchema
from app.ai.transport import ChatCompletion, ChatMessage, post_json
from app.core.errors import AIUnavailableError


class CloudflareWorkersAITransport:
    def __init__(
        self,
        base_url: str,
        account_id: str,
        api_token: str,
        timeout: float,
        client: httpx.Client | None = None,
    ) -> None:
        self._base = f"{base_url.rstrip('/')}/accounts/{account_id}/ai/run/"
        self._headers = {"Authorization": f"Bearer {api_token}"}
        self._client = client or httpx.Client(timeout=timeout)

    def __repr__(self) -> str:
        return f"CloudflareWorkersAITransport(base={self._base!r})"

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
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_schema is not None:
            # Workers AI JSON mode takes the schema itself under "json_schema".
            body["response_format"] = {"type": "json_schema", "json_schema": response_schema.schema}
        elif json_mode:
            body["response_format"] = {"type": "json_object"}
        response = post_json(self._client, self._base + model, body, self._headers)
        return _parse(response, model)


def _parse(response: httpx.Response, model: str) -> ChatCompletion:
    try:
        payload = response.json()
        if payload.get("success") is False:
            raise ValueError("unsuccessful")
        result = payload["result"]
        truncated = False
        if "response" in result:
            content = result["response"]
        else:  # models that answer in the OpenAI shape inside "result"
            choice = result["choices"][0]
            content = choice["message"]["content"]
            truncated = choice.get("finish_reason") == "length"
        if isinstance(content, (dict, list)):
            # In JSON mode Workers AI may return the object already parsed.
            content = json.dumps(content)
        if not isinstance(content, str):
            raise TypeError("content is not a string")
    except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
        raise AIUnavailableError(
            "The AI provider's response wasn't in the expected format.",
            details={"reason": "bad_response", "failure": FailureKind.PROVIDER_UNAVAILABLE},
        ) from exc
    return ChatCompletion(content=content, served_model=model, truncated=truncated)
