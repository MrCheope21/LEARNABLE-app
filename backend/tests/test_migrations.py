"""Alembic migrations must produce exactly the schema the models describe.

Catches the classic drift bug: a model column added/changed without a matching migration, which
would pass every other test (they build the schema from the models via create_all).
"""

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
