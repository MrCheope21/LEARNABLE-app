"""Shared fixtures.

Database backend, in priority order:
  1. TEST_DATABASE_URL env var (e.g. a Postgres service in CI)
  2. `pytest --postgres`: a throwaway local PostgreSQL started via pgserver (no system install)
  3. default: in-memory SQLite

Run with Postgres before trusting a schema change — SQLite doesn't enforce VARCHAR lengths or
timezones, and several bugs in this codebase were ones only Postgres surfaces.
"""

import os
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

# Must be set before anything calls get_settings(); an explicit test value keeps runs hermetic
# regardless of what's in a developer's local .env.
os.environ["AUTH_SECRET"] = "test-only-secret-" + "x" * 40
# The startup sweep would otherwise run against the default database, not the test one.
os.environ["JOB_RECOVERY_INTERVAL_SECONDS"] = "0"

from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # registers every model on Base.metadata
from app.ai.factory import get_ai_provider
from app.ai.mock import MockAIProvider
from app.core.rate_limit import limiter
from app.db.base import Base
from app.db.session import create_engine_for_url, get_db, get_session_factory
from app.main import app
from app.storage.documents import LocalDocumentStorage, get_document_storage

DEFAULT_PASSWORD = "correct-horse-battery-staple"

AuthHeaders = Callable[..., dict[str, str]]


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--postgres",
        action="store_true",
        help="Run against a throwaway local PostgreSQL (via pgserver) instead of SQLite.",
    )


def pytest_report_header(config: pytest.Config) -> str:
    if os.environ.get("TEST_DATABASE_URL"):
        return "database: TEST_DATABASE_URL"
    if config.getoption("--postgres"):
        return "database: PostgreSQL (throwaway, via pgserver)"
    return "database: SQLite in-memory (run with --postgres before trusting schema changes)"


@pytest.fixture(scope="session")
def database_url(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory) -> str:
    if url := os.environ.get("TEST_DATABASE_URL"):
        return url
    if request.config.getoption("--postgres"):
        import pgserver

        server = pgserver.get_server(tmp_path_factory.mktemp("pgdata"), cleanup_mode="stop")
        return server.get_uri()
    return "sqlite:///:memory:"


@pytest.fixture(scope="session")
def engine(database_url: str) -> Iterator[Engine]:
    if database_url == "sqlite:///:memory:":
        # StaticPool: every checkout shares one connection. SQLite's :memory: database is
        # per-connection, so a normal pool would give each checkout its own empty database.
        engine = create_engine_for_url(database_url, poolclass=StaticPool)
    else:
        engine = create_engine_for_url(database_url)
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def _fresh_rate_limits() -> None:
    """Every test starts with no attempts counted (the limiter is process-wide)."""
    limiter.reset()


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def storage(tmp_path: Path) -> LocalDocumentStorage:
    """A per-test document store, so tests never touch backend/var or each other's files."""
    return LocalDocumentStorage(tmp_path / "storage")


@pytest.fixture
def ai_provider() -> MockAIProvider:
    """The AIProvider every request gets. Tests never call a real model (spec §76); to script
    a different answer or a failure, override `get_ai_provider` with another MockAIProvider."""
    return MockAIProvider()


@pytest.fixture
def client(
    db_session: Session, engine: Engine, storage: LocalDocumentStorage, ai_provider: MockAIProvider
) -> Iterator[TestClient]:
    def _get_db_override() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = _get_db_override
    # Background tasks (document processing) open their own sessions; point them at the test DB.
    app.dependency_overrides[get_session_factory] = lambda: sessionmaker(
        bind=engine, autoflush=False
    )
    app.dependency_overrides[get_document_storage] = lambda: storage
    app.dependency_overrides[get_ai_provider] = lambda: ai_provider
    # TestClient runs background tasks before returning, so a document is fully processed by the
    # time an upload call returns.
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers(client: TestClient) -> AuthHeaders:
    """Returns a function that registers a fresh user and returns their Authorization header."""

    def _make(email: str, password: str = DEFAULT_PASSWORD) -> dict[str, str]:
        register = client.post("/api/v1/auth/register", json={"email": email, "password": password})
        assert register.status_code == 201, register.text
        login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert login.status_code == 200, login.text
        return {"Authorization": f"Bearer {login.json()['access_token']}"}

    return _make
