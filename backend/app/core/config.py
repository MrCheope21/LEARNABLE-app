"""Application configuration, loaded from environment variables and the repo-root `.env`."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent

_MIN_SECRET_LENGTH = 32
_KNOWN_PLACEHOLDER_SECRETS = {"change-me", "changeme", "secret", "dev", "test"}

# AI_PROVIDER values (docs/AI.md §3). The vendor names are labels for an OpenAI-compatible
# endpoint: they record which vendor served a call, but carry no hard-coded URL or behavior.
AI_PROVIDER_MOCK = "mock"
AI_PROVIDER_OPENAI_COMPATIBLE = "openai_compatible"
# AI_PROVIDER=router: per-operation routes over several providers (docs/FREE_AI_ROUTING.md).
AI_PROVIDER_ROUTER = "router"
OPENAI_COMPATIBLE_ALIASES = frozenset({"qwen", "kimi", "glm"})
# Providers with a known endpoint in app/ai/catalog.py: AI_BASE_URL is optional for them.
CATALOG_PROVIDERS = frozenset(
    {
        "groq",
        "mistral",
        "gemini",
        "openrouter",
        "nvidia",
        "cloudflare",
        "cohere",
        "alibaba_model_studio",
        "tencent_tokenhub",
        "siliconflow",
        "deepseek",
        "moonshot",
        "zai",
        "minimax",
    }
)
AI_PROVIDERS = frozenset(
    {
        AI_PROVIDER_MOCK,
        AI_PROVIDER_ROUTER,
        AI_PROVIDER_OPENAI_COMPATIBLE,
        *OPENAI_COMPATIBLE_ALIASES,
        *CATALOG_PROVIDERS,
    }
)
FALLBACK_PROVIDERS = AI_PROVIDERS - {AI_PROVIDER_ROUTER}


def normalize_database_url(url: str) -> str:
    """Route bare Postgres URLs to the psycopg (v3) driver we actually install.

    SQLAlchemy maps `postgresql://` to psycopg2, which isn't a dependency; managed hosts also hand
    out `postgres://` URLs. Both get rewritten so any standard Postgres URL just works.
    """
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    database_url: str = f"sqlite:///{(BACKEND_DIR / 'dev.db').as_posix()}"

    # Required, no default: a server must never run with a guessable JWT signing key.
    auth_secret: SecretStr
    auth_access_token_expire_minutes: int = Field(default=60, gt=0)
    # Where the web app is served: password reset links point here.
    # On Render, the service's own public address (RENDER_EXTERNAL_URL) unless PUBLIC_APP_URL
    # says otherwise: the web app is served from the same origin there.
    public_app_url: str = Field(
        default_factory=lambda: os.environ.get("RENDER_EXTERNAL_URL") or "http://localhost:5173"
    )
    # The built web client (web/dist). When set, this server also serves it, on the same origin
    # as /api (app/web.py; the production image sets it). Unset in development: Vite serves it.
    web_dist_dir: Path | None = None
    password_reset_ttl_minutes: int = Field(default=30, gt=0, le=24 * 60)
    # Outgoing email (app/email/sender.py). console: written to the server log (development).
    email_backend: Literal["console", "smtp"] = "console"
    smtp_host: str = ""
    smtp_port: int = Field(default=587, gt=0)
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    # The From address, e.g. "LEARNABLE <no-reply@example.com>".
    smtp_from: str = ""
    smtp_starttls: bool = True

    # Runtime AI provider (see docs/AI.md) — intentionally provider-agnostic, never hard-coded.
    # Empty means AI features are off: the server runs, and AI endpoints answer 503.
    ai_provider: str = ""
    ai_base_url: str = ""
    ai_api_key: SecretStr = SecretStr("")
    ai_model: str = ""
    ai_timeout: float = Field(default=60, gt=0)
    ai_temperature: float = Field(default=0.2, ge=0, le=2)
    ai_max_tokens: int = Field(default=8192, gt=0)
    # Ask for `response_format: json_object`. Turn off for endpoints that reject the parameter;
    # the output is schema-validated either way.
    ai_json_mode: bool = True
    # Most source text sent in one call. ~4 characters per token, so the default (~15k tokens)
    # plus the prompt and the answer fits a 32k-token context window.
    ai_max_context_chars: int = Field(default=60_000, ge=2_000)
    # Optional per-operation models (spec §34); empty falls back to AI_MODEL.
    ai_model_extraction: str = ""
    ai_model_generation: str = ""
    ai_model_evaluation: str = ""
    ai_model_exam: str = ""
    # Fallback providers (docs/AI.md §3), tried in order when the one before is unavailable or
    # keeps answering invalid output. Each is a complete, independent endpoint: a different
    # vendor protects against one vendor's outage. They share the timeout/temperature/token
    # settings above. Empty AI_FALLBACK1_PROVIDER: no fallback.
    ai_fallback1_provider: str = ""
    ai_fallback1_base_url: str = ""
    ai_fallback1_api_key: SecretStr = SecretStr("")
    ai_fallback1_model: str = ""
    ai_fallback2_provider: str = ""
    ai_fallback2_base_url: str = ""
    ai_fallback2_api_key: SecretStr = SecretStr("")
    ai_fallback2_model: str = ""

    # --- Cost, data and routing policy (docs/FREE_AI_ROUTING.md) ---
    # FREE_ONLY: only models marked free_only_eligible ever run; when none can answer, calls
    # fail with free_capacity_exhausted. A paid endpoint is never called.
    ai_cost_policy: Literal["FREE_ONLY", "FREE_FIRST", "ANY_CONFIGURED"] = "FREE_ONLY"
    # private: only models whose terms the owner approved for private material run.
    ai_data_policy: Literal["development", "private"] = "development"
    # Comma-separated "provider:model" lists (model IDs may contain ':' and '/').
    ai_free_models: str = ""
    ai_private_approved_models: str = ""
    ai_evaluation_approved_models: str = ""
    # true: answer evaluation only uses benchmark-approved models.
    ai_evaluation_require_approved: bool = False
    # AI_PROVIDER=router: ordered candidates per operation; empty uses the catalog's defaults.
    ai_route_curriculum_generation: str = ""
    ai_route_concept_extraction: str = ""
    ai_route_learning_item_generation: str = ""
    ai_route_question_generation: str = ""
    ai_route_answer_evaluation: str = ""
    ai_route_feedback_generation: str = ""
    # Router credentials: one per provider. CI maps its own secret names onto these.
    ai_groq_api_key: SecretStr = SecretStr("")
    ai_mistral_api_key: SecretStr = SecretStr("")
    ai_gemini_api_key: SecretStr = SecretStr("")
    ai_openrouter_api_key: SecretStr = SecretStr("")
    ai_nvidia_api_key: SecretStr = SecretStr("")
    ai_cloudflare_api_token: SecretStr = SecretStr("")
    ai_cohere_api_key: SecretStr = SecretStr("")
    ai_alibaba_model_studio_api_key: SecretStr = SecretStr("")
    ai_tencent_tokenhub_api_key: SecretStr = SecretStr("")
    ai_siliconflow_api_key: SecretStr = SecretStr("")
    # Direct vendor APIs (paid or temporary credits): not needed for FREE_ONLY.
    ai_deepseek_api_key: SecretStr = SecretStr("")
    ai_moonshot_api_key: SecretStr = SecretStr("")
    ai_zai_api_key: SecretStr = SecretStr("")
    ai_minimax_api_key: SecretStr = SecretStr("")
    # Not a secret: identifies the Cloudflare account in the Workers AI URL.
    ai_cloudflare_account_id: str = ""
    # Not a secret: optional Alibaba Model Studio workspace (sent as X-DashScope-WorkSpace).
    ai_alibaba_workspace_id: str = ""
    # Billing guards the OWNER confirms after enabling them in the provider's console. Until
    # then that provider's models never run under FREE_ONLY, because its free quota would roll
    # over into paid use (docs/FREE_AI_ROUTING.md §2b).
    ai_alibaba_free_only_confirmed: bool = False
    ai_tencent_free_only_confirmed: bool = False
    # Optional endpoint overrides (e.g. a regional endpoint).
    ai_groq_base_url: str = ""
    ai_mistral_base_url: str = ""
    ai_gemini_base_url: str = ""
    ai_openrouter_base_url: str = ""
    ai_nvidia_base_url: str = ""
    ai_cloudflare_base_url: str = ""
    ai_cohere_base_url: str = ""
    ai_alibaba_model_studio_base_url: str = ""
    ai_tencent_tokenhub_base_url: str = ""
    ai_siliconflow_base_url: str = ""
    ai_deepseek_base_url: str = ""
    ai_moonshot_base_url: str = ""
    ai_zai_base_url: str = ""
    ai_minimax_base_url: str = ""

    # Knowledge Repository files (docs/PROJECT_SPEC.md §16, docs/DEPLOYMENT.md §3).
    # local: a directory (persistent only if it's on a persistent volume).
    # s3: a private bucket on any S3-compatible service (AWS S3, Cloudflare R2, Backblaze B2,
    # MinIO...). Files are only ever served through the API after an ownership check.
    storage_backend: Literal["local", "s3"] = "local"
    storage_local_dir: Path = BACKEND_DIR / "var" / "documents"
    # Empty for AWS S3 itself; the service's endpoint URL otherwise.
    storage_endpoint: str = ""
    storage_bucket: str = ""
    storage_region: str = ""
    storage_access_key_id: str = ""
    storage_secret_access_key: SecretStr = SecretStr("")
    # Optional key prefix inside the bucket, e.g. "learnable/".
    storage_prefix: str = ""
    max_upload_mb: int = Field(default=50, gt=0)

    # Interrupted background jobs (see app/services/recovery.py) are swept at startup and then
    # every this many seconds. 0 disables the sweep (tests drive it directly).
    job_recovery_interval_seconds: float = Field(default=60, ge=0)
    # Attempt limits on sign-in, sign-up, password and AI-heavy endpoints (app/core/rate_limit.py).
    rate_limits_enabled: bool = True

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        return normalize_database_url(value)

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper_log_level(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("ai_provider", "ai_fallback1_provider", "ai_fallback2_provider")
    @classmethod
    def _normalize_ai_provider(cls, value: str) -> str:
        value = value.strip().lower()
        if value and value not in AI_PROVIDERS:
            raise ValueError(
                f"AI provider must be empty or one of: {', '.join(sorted(AI_PROVIDERS))}"
            )
        return value

    @field_validator("ai_cost_policy", mode="before")
    @classmethod
    def _upper_cost_policy(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("ai_data_policy", mode="before")
    @classmethod
    def _lower_data_policy(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _require_smtp_settings(self) -> Self:
        if self.email_backend == "smtp":
            missing = [
                name
                for name, value in (("SMTP_HOST", self.smtp_host), ("SMTP_FROM", self.smtp_from))
                if not value.strip()
            ]
            if missing:
                raise ValueError(f"EMAIL_BACKEND=smtp requires {' and '.join(missing)}")
        return self

    @model_validator(mode="after")
    def _require_built_web_app(self) -> Self:
        if self.web_dist_dir is not None and not (self.web_dist_dir / "index.html").is_file():
            raise ValueError(
                f"WEB_DIST_DIR={self.web_dist_dir} has no index.html (build web first)"
            )
        return self

    @model_validator(mode="after")
    def _require_storage_bucket(self) -> Self:
        if self.storage_backend == "s3" and not self.storage_bucket.strip():
            raise ValueError("STORAGE_BACKEND=s3 requires STORAGE_BUCKET")
        return self

    @model_validator(mode="after")
    def _require_ai_endpoints(self) -> Self:
        for prefix, provider, base_url, model in (
            ("AI", self.ai_provider, self.ai_base_url, self.ai_model),
            (
                "AI_FALLBACK1",
                self.ai_fallback1_provider,
                self.ai_fallback1_base_url,
                self.ai_fallback1_model,
            ),
            (
                "AI_FALLBACK2",
                self.ai_fallback2_provider,
                self.ai_fallback2_base_url,
                self.ai_fallback2_model,
            ),
        ):
            if provider in (AI_PROVIDER_MOCK, AI_PROVIDER_ROUTER, ""):
                continue
            required = [("MODEL", model)]
            if provider not in CATALOG_PROVIDERS:
                required.insert(0, ("BASE_URL", base_url))
            missing = [f"{prefix}_{name}" for name, value in required if not value.strip()]
            if provider == "cloudflare" and not self.ai_cloudflare_account_id.strip():
                missing.append("AI_CLOUDFLARE_ACCOUNT_ID")
            if missing:
                raise ValueError(f"{prefix}_PROVIDER={provider} requires {' and '.join(missing)}")
        if (self.ai_fallback1_provider or self.ai_fallback2_provider) and not self.ai_provider:
            raise ValueError("AI fallbacks are set but AI_PROVIDER is empty")
        if self.ai_fallback2_provider and not self.ai_fallback1_provider:
            raise ValueError("AI_FALLBACK2_PROVIDER is set without AI_FALLBACK1_PROVIDER")
        if AI_PROVIDER_ROUTER in (self.ai_fallback1_provider, self.ai_fallback2_provider):
            raise ValueError("router can only be AI_PROVIDER, not a fallback")
        if self.ai_provider == AI_PROVIDER_ROUTER and self.ai_fallback1_provider:
            raise ValueError("AI_PROVIDER=router takes its fallbacks from AI_ROUTE_* routes")
        for name in (
            "ai_route_curriculum_generation",
            "ai_route_concept_extraction",
            "ai_route_learning_item_generation",
            "ai_route_question_generation",
            "ai_route_answer_evaluation",
            "ai_route_feedback_generation",
            "ai_free_models",
            "ai_private_approved_models",
            "ai_evaluation_approved_models",
        ):
            for entry in parse_model_list(getattr(self, name)):
                if entry[0] not in FALLBACK_PROVIDERS:
                    raise ValueError(f"{name.upper()}: unknown provider '{entry[0]}'")
        return self

    @field_validator("auth_secret")
    @classmethod
    def _reject_weak_secret(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if raw.lower() in _KNOWN_PLACEHOLDER_SECRETS or len(raw) < _MIN_SECRET_LENGTH:
            raise ValueError(
                f"AUTH_SECRET must be a random string of at least {_MIN_SECRET_LENGTH} "
                'characters. Generate one with: python -c "import secrets; '
                'print(secrets.token_urlsafe(48))"'
            )
        return value


def parse_model_list(value: str) -> list[tuple[str, str]]:
    """ "groq:openai/gpt-oss-120b, openrouter:x/y:free" → [("groq", "openai/gpt-oss-120b"), ...].
    Split on the first ':' only: model IDs may contain ':' (OpenRouter's ':free') and '/'."""
    entries = []
    for raw in value.split(","):
        item = raw.strip()
        if not item:
            continue
        provider, sep, model = item.partition(":")
        if not sep or not provider.strip() or not model.strip():
            raise ValueError(f"expected 'provider:model', got '{item}'")
        entries.append((provider.strip().lower(), model.strip()))
    return entries


@lru_cache
def get_settings() -> Settings:
    return Settings()
