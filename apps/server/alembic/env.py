"""Alembic environment: sync engine over the same database file as the app.

The URL comes from the runtime config (infra/migrations.py) or the
POMOTIVATO_DB env var for CLI usage; schema truth is Base.metadata in
pomotivato.infra.orm, keeping autogenerate honest.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

_SERVER_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_SERVER_ROOT / "src"))

from pomotivato.infra.db import default_db_path, sync_url  # noqa: E402
from pomotivato.infra.orm import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

if not config.get_main_option("sqlalchemy.url"):
    raw = os.environ.get("POMOTIVATO_DB")
    config.set_main_option("sqlalchemy.url", sync_url(Path(raw) if raw else default_db_path()))


def run_migrations_offline() -> None:
    """Emit SQL for the target URL without a live DB connection."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live connection (batch mode for SQLite)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
