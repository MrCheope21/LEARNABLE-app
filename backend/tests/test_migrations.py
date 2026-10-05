"""Alembic migrations must produce exactly the schema the models describe.

Catches the classic drift bug: a model column added/changed without a matching migration, which
would pass every other test (they build the schema from the models via create_all).
"""

import uuid

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect, text

import app.models  # noqa: F401
from app.core.config import BACKEND_DIR
from app.db.base import Base
from app.db.session import create_engine_for_url


@pytest.fixture
def migration_engine(database_url: str, engine: Engine, tmp_path):
    if database_url.startswith("sqlite"):
        # A file DB: migrations open their own transactions, which don't mix with the shared
        # in-memory connection the other tests use.
        fresh = create_engine_for_url(f"sqlite:///{(tmp_path / 'migrations.db').as_posix()}")
        yield fresh
        fresh.dispose()
    else:
        yield engine
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
        Base.metadata.drop_all(engine)


def _alembic_config(connection) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.attributes["connection"] = connection
    config.attributes["configure_logger"] = False
    return config


def test_migrations_match_models_and_downgrade_cleanly(migration_engine: Engine):
    with migration_engine.begin() as connection:
        command.upgrade(_alembic_config(connection), "head")
        diff = compare_metadata(
            MigrationContext.configure(connection, opts={"compare_type": True}), Base.metadata
        )
        assert diff == [], f"models and migrations have drifted: {diff}"

    with migration_engine.begin() as connection:
        command.downgrade(_alembic_config(connection), "base")
        remaining = set(inspect(connection).get_table_names()) - {"alembic_version"}
        assert remaining == set()


def test_migrations_keep_existing_data(migration_engine: Engine):
    """On SQLite, batch mode rebuilds a table (copy, drop, rename). With foreign keys enforced,
    dropping the old `courses` table cascaded into every chapter, question and document. The
    marketplace migration rebuilds `courses`: a course's content must survive it."""
    user, course, chapter = uuid.uuid4().hex, uuid.uuid4().hex, uuid.uuid4().hex
    now = "2026-10-01 10:00:00"
    with migration_engine.connect() as connection:
        command.upgrade(_alembic_config(connection), "a9c3e5f7b1d2")
        connection.commit()
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.execute(
            text(
                "INSERT INTO users (id, email, hashed_password, created_at) "
                "VALUES (:id, 'keep@example.com', 'x', :now)"
            ),
            {"id": user, "now": now},
        )
        connection.execute(
            text(
                "INSERT INTO courses (id, user_id, title, description, language, created_at, "
                "updated_at) VALUES (:id, :user, 'Commercialista', '', 'it', :now, :now)"
            ),
            {"id": course, "user": user, "now": now},
        )
        connection.execute(
            text(
                'INSERT INTO chapters (id, course_id, title, description, "order", created_at, '
                "updated_at) VALUES (:id, :course, 'Diritto commerciale', '', 0, :now, :now)"
            ),
            {"id": chapter, "course": course, "now": now},
        )
        connection.commit()
    with migration_engine.connect() as connection:
        command.upgrade(_alembic_config(connection), "head")
        titles = connection.execute(text("SELECT title FROM chapters")).scalars().all()
    assert titles == ["Diritto commerciale"]
