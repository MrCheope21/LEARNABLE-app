"""JSON Schema for structured output, derived from the application's Pydantic schemas.

The Pydantic model stays authoritative: every answer is validated against it locally, whatever
the provider promised. The schema sent to a provider is a transport hint, adapted to what
constrained decoding accepts (docs/FREE_AI_ROUTING.md §6):

- `$ref`s are inlined (several providers don't resolve `$defs`);
- every property is listed in `required` and objects get `additionalProperties: false` (strict
  mode requires both; fields with defaults simply have to be emitted);
- length/size/range keywords, titles and defaults are removed, because strict decoders reject
  many of them. Those limits are still enforced by local validation, so nothing is weakened.
"""

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

_DROP = {
    "title",
    "default",
    "minLength",
    "maxLength",
    "minItems",
    "maxItems",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "pattern",
    "format",
    "examples",
}


@dataclass(frozen=True)
class ResponseSchema:
    name: str
    schema: dict[str, Any]
    strict: bool


def response_schema(model: type[BaseModel], *, strict: bool) -> ResponseSchema:
    raw = model.model_json_schema()
    defs = raw.get("$defs", {})
    schema = _clean(_inline(raw, defs))
    return ResponseSchema(name=model.__name__, schema=schema, strict=strict)


def _inline(node: Any, defs: dict[str, Any]) -> Any:
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            return _inline(defs[ref.removeprefix("#/$defs/")], defs)
        return {k: _inline(v, defs) for k, v in node.items() if k != "$defs"}
    if isinstance(node, list):
        return [_inline(v, defs) for v in node]
    return node


def _clean(node: Any) -> Any:
    if isinstance(node, list):
        return [_clean(v) for v in node]
    if not isinstance(node, dict):
        return node
    cleaned: dict[str, Any] = {}
    for key, value in node.items():
        if key == "properties" and isinstance(value, dict):
            # Field names, not keywords: a field may be called "title" or "default".
            cleaned[key] = {name: _clean(sub) for name, sub in value.items()}
        elif key not in _DROP:
            cleaned[key] = _clean(value)
    if cleaned.get("type") == "object" and "properties" in cleaned:
        cleaned["required"] = list(cleaned["properties"].keys())
        cleaned["additionalProperties"] = False
    return cleaned
