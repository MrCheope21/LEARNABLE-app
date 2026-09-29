"""SQLAlchemy engine/session setup.

The engine is created lazily on first use, not at import time, so importing the app (e.g. in tests
or Alembic) never opens a connection to — or creates — the configured database as a side effect.
"""

from collections.abc import Generator
from functools import lru_cache
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings, normalize_database_url


def _enable_sqlite_foreign_keys(dbapi_connection: Any, _connection_record: Any) -> None:
    # SQLite ignores FOREIGN KEY constraints (including ON DELETE CASCADE) unless enabled per
    # connection; without this, SQLite-backed tests would pass on data Postgres would reject.
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_engine_for_url(url: str, **kwargs: Any) -> Engine:
    url = normalize_database_url(url)
    is_sqlite = url.startswith("sqlite")
    connect_args = {"check_same_thread": False} if is_sqlite else {}
    engine = create_engine(url, connect_args=connect_args, **kwargs)
    if is_sqlite:
        event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    return engine


@lru_cache
def get_engine() -> Engine:
    return create_engine_for_url(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False)


def get_db() -> Generator[Session, None, None]:
    db = _session_factory()()
    try:
        yield db
    finally:
        db.close()


def get_session_factory() -> sessionmaker[Session]:
    """For work that outlives the request (background tasks), which must open its own session
    rather than reuse the request's. A dependency so tests can point it at the test database."""
    return _session_factory()
