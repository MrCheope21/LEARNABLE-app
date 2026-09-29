import pytest
from pydantic import ValidationError

from app.core.config import Settings

STRONG_SECRET = "s" * 48


def test_missing_auth_secret_refuses_to_load(monkeypatch):
    monkeypatch.delenv("AUTH_SECRET", raising=False)
    with pytest.raises(ValidationError, match="auth_secret"):
        Settings(_env_file=None)


@pytest.mark.parametrize("secret", ["change-me", "CHANGE-ME", "", "short-but-random-9f3a"])
def test_weak_auth_secret_refuses_to_load(secret):
    with pytest.raises(ValidationError, match="AUTH_SECRET must be"):
        Settings(_env_file=None, auth_secret=secret)


def test_secret_is_masked_in_repr():
    settings = Settings(_env_file=None, auth_secret=STRONG_SECRET)
    assert STRONG_SECRET not in repr(settings)


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("postgresql://u:p@db:5432/app", "postgresql+psycopg://u:p@db:5432/app"),
        ("postgres://u:p@db:5432/app", "postgresql+psycopg://u:p@db:5432/app"),
        ("postgresql+psycopg://u:p@db:5432/app", "postgresql+psycopg://u:p@db:5432/app"),
        ("sqlite:///./dev.db", "sqlite:///./dev.db"),
    ],
)
def test_database_url_uses_installed_postgres_driver(given, expected):
    settings = Settings(_env_file=None, auth_secret=STRONG_SECRET, database_url=given)
    assert settings.database_url == expected


@pytest.mark.parametrize(("given", "expected"), [("info", "INFO"), (" debug ", "DEBUG")])
def test_log_level_is_normalized(given, expected):
    assert (
        Settings(_env_file=None, auth_secret=STRONG_SECRET, log_level=given).log_level == expected
    )


def test_unknown_log_level_refuses_to_load():
    with pytest.raises(ValidationError, match="log_level"):
        Settings(_env_file=None, auth_secret=STRONG_SECRET, log_level="LOUD")
