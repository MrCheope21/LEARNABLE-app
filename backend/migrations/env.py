from logging.config import fileConfig
from typing import Any, Literal

from alembic import context
from alembic.autogenerate.api import AutogenContext
from sqlalchemy import pool
from sqlalchemy.engine import Connection

import app.models  # noqa: F401  (registers every model on Base.metadata)
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import create_engine_for_url
from app.db.types import UTCDateTime

config = context.config

# Tests run migrations in-process and pass configure_logger=False so Alembic's ini logging setup
# doesn't clobber pytest's log capture.
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _render_item(type_: str, obj: Any, _autogen_context: AutogenContext) -> str | Literal[False]:
    # Render app-specific column types as plain SQLAlchemy types, so migration files never import
    # app code (a migration must keep working even after the app's types change or move).
    if type_ == "type" and isinstance(obj, UTCDateTime):
        return "sa.DateTime(timezone=True)"
    return False


def _run(connection: Connection) -> None:
    sqlite = connection.dialect.name == "sqlite"
    # The PRAGMA only works outside a transaction; a caller that already opened one (the
    # migration tests) is left as it is.
    guard_foreign_keys = sqlite and not connection.in_transaction()
    if guard_foreign_keys:
        # SQLite can't ALTER most things in place: batch mode rebuilds the table (copy, drop the
        # old one, rename). With foreign keys enforced (app/db/session.py turns them on for every
        # connection), dropping the old table cascades into every row that references it:
        # rebuilding `courses` deleted all chapters, questions and documents. Off for the
        # migration (it must be set outside a transaction), checked, and back on afterwards.
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        # The PRAGMA opened a transaction; end it, or Alembic would join it and never commit.
        connection.commit()
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_item=_render_item,
        compare_type=True,
        render_as_batch=sqlite,
    )
    try:
        with context.begin_transaction():
            context.run_migrations()
            if guard_foreign_keys:
                broken = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
                if broken:
                    raise RuntimeError(f"migration left rows with broken references: {broken[:5]}")
    finally:
        if guard_foreign_keys:
            connection.commit()
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        render_item=_render_item,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # A caller (e.g. the migration test) may hand us an already-open connection.
    external_connection = config.attributes.get("connection")
    if external_connection is not None:
        _run(external_connection)
        return

    engine = create_engine_for_url(get_settings().database_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        _run(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
