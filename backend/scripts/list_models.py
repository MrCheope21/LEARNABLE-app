"""Lists the model IDs a provider currently serves to this key (docs/FREE_AI_ROUTING.md §8).

    AI_PROVIDER=groq AI_API_KEY=... python scripts/list_models.py

Run before benchmarking or allowlisting: vendor catalogs change, and model IDs in
app/ai/catalog.py are only as good as the last check. Prints IDs (and, where the vendor says so,
whether a model is free) and nothing else: never the key or response headers.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from app.ai.catalog import PROVIDERS, TransportKind
from app.core.config import Settings


def model_ids(settings: Settings, client: httpx.Client) -> list[str]:
    provider = settings.ai_provider
    spec = PROVIDERS[provider]
    base = (settings.ai_base_url or spec.default_base_url or "").rstrip("/")
    headers = {"Authorization": f"Bearer {settings.ai_api_key.get_secret_value()}"}
    if spec.transport is TransportKind.CLOUDFLARE:
        url = f"{base}/accounts/{settings.ai_cloudflare_account_id}/ai/models/search"
        response = client.get(
            url, headers=headers, params={"task": "Text Generation", "per_page": 200}
        )
        response.raise_for_status()
        return sorted(_cloudflare_line(m) for m in response.json().get("result", []))
    response = client.get(f"{base}/models", headers=headers)
    response.raise_for_status()
    data = response.json()
    entries: list[dict[str, Any]] = (
        (data.get("data") or data.get("models") or []) if isinstance(data, dict) else data
    )
    return sorted(_openai_line(provider, m) for m in entries)


def _openai_line(provider: str, model: dict[str, Any]) -> str:
    model_id = str(model.get("id") or model.get("name"))
    if provider == "openrouter":
        pricing = model.get("pricing") or {}
        free = all(str(pricing.get(k, "1")) in ("0", "0.0") for k in ("prompt", "completion"))
        return f"{model_id}{'  [free]' if free else ''}"
    return model_id


def _cloudflare_line(model: dict[str, Any]) -> str:
    properties = {p.get("property_id"): p.get("value") for p in model.get("properties", [])}
    tags = [k for k in ("beta", "planned_deprecation_date") if properties.get(k)]
    return f"{model.get('name')}{'  [' + ', '.join(tags) + ']' if tags else ''}"


def main() -> int:
    settings = Settings()
    if (
        settings.ai_provider not in PROVIDERS
        or PROVIDERS[settings.ai_provider].transport is TransportKind.MOCK
    ):
        print(
            "Set AI_PROVIDER to a catalog provider (groq, mistral, gemini, ...).", file=sys.stderr
        )
        return 2
    try:
        with httpx.Client(timeout=30) as client:
            ids = model_ids(settings, client)
    except httpx.HTTPStatusError as exc:
        # Status only: the body can echo request details.
        print(f"Listing failed with HTTP {exc.response.status_code}.", file=sys.stderr)
        return 1
    except httpx.HTTPError:
        print("Listing failed: the provider couldn't be reached.", file=sys.stderr)
        return 1
    print(f"{len(ids)} models from {settings.ai_provider}:")
    for line in ids:
        print(f"  {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
