from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, EmailStr, Field


def _strip(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


# Emails are compared and stored lowercased, so "B@example.com" and "b@example.com" are the same
# account. (RFC 5321 technically allows case-sensitive local parts; no real mail provider uses it.)
NormalizedEmail = Annotated[
    EmailStr, BeforeValidator(_strip), AfterValidator(lambda email: email.lower())
]

# 12+ characters per OWASP ASVS 2.1.1. The upper bound caps hashing cost per request.
NewPassword = Annotated[str, Field(min_length=12, max_length=128)]


class _AuthInput(BaseModel):
    # Deliberately NOT InputModel: that strips whitespace from every string, which would silently
    # change passwords with leading/trailing spaces.
    model_config = ConfigDict(extra="forbid")


def _valid_zone(value: str | None) -> str | None:
    # Imported here: app.services pulls in the models, which auth schemas mustn't depend on.
    from app.services.rewards.service import is_valid_zone

    if value is not None and not is_valid_zone(value):
        raise ValueError("unknown IANA timezone, e.g. Europe/Rome")
    return value


# An IANA zone name ("Europe/Rome"); decides the user's calendar day.
Timezone = Annotated[str, Field(min_length=1, max_length=64), AfterValidator(_valid_zone)]
DailyGoal = Annotated[int, Field(ge=1, le=500)]
# Interface languages the clients ship: English, Italian, Spanish, French, German, Chinese
# (Simplified), Japanese, Arabic, Hindi.
Language = Literal["en", "it", "es", "fr", "de", "zh", "ja", "ar", "hi"]


class UserCreate(_AuthInput):
    email: NormalizedEmail
    password: NewPassword
    # The device's zone; UTC when omitted (it can be changed later).
    timezone: Timezone | None = None
    # The language the sign-up page was shown in; English when omitted.
    language: Language = "en"


class UserLogin(_AuthInput):
    email: NormalizedEmail
    # No policy check at login: the policy can tighten later without locking out older accounts.
    password: Annotated[str, Field(min_length=1, max_length=128)]


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    timezone: str
    # Completed answers per day.
    daily_goal: int
    language: Language
    display_name: str | None


class UserPreferencesUpdate(_AuthInput):
    timezone: Timezone | None = None
    daily_goal: DailyGoal | None = None
    language: Language | None = None
    # An empty string clears it.
    display_name: Annotated[str, Field(max_length=80)] | None = None


class PasswordResetRequest(_AuthInput):
    email: NormalizedEmail


class PasswordResetConfirm(_AuthInput):
    token: Annotated[str, Field(min_length=20, max_length=200)]
    new_password: NewPassword


class PasswordChange(_AuthInput):
    current_password: Annotated[str, Field(min_length=1, max_length=128)]
    new_password: NewPassword


class MessageRead(BaseModel):
    detail: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 — OAuth token type label, not a secret
