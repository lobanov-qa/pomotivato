"""Async database infrastructure (spec 02 §3).

One process owns one SQLite file; sessions are created per request via the
repository layer later (E2 e2-repositories). Foreign keys must be enabled
per connection because SQLite ignores them by default.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

ASYNC_URL_PREFIX = "sqlite+aiosqlite:///"
SYNC_URL_PREFIX = "sqlite:///"

DB_PATH_ENV = "POMOTIVATO_DB"


def default_db_path() -> Path:
    """Resolve the database file from env or the XDG data directory."""
    raw = os.environ.get(DB_PATH_ENV)
    if raw:
        return Path(raw).expanduser()
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return data_home / "pomotivato" / "pomotivato.db"


def async_url(db_path: Path) -> str:
    """Build the aiosqlite URL the app uses at runtime."""
    return f"{ASYNC_URL_PREFIX}{db_path}"


def sync_url(db_path: Path) -> str:
    """Build the plain sqlite URL Alembic migrations use (sync driver)."""
    return f"{SYNC_URL_PREFIX}{db_path}"


def enable_sqlite_pragmas(engine: Engine) -> None:
    """Attach a per-connection handler turning on WAL and FK enforcement.

    `engine.name` is the dialect ("sqlite") for both the sync and the
    aiosqlite drivers; get_driver_name() would return "aiosqlite" here.
    """
    if engine.name != "sqlite":
        return
    event.listen(engine, "connect", _set_sqlite_pragmas)


def _set_sqlite_pragmas(dbapi_connection: object, _record: object) -> None:
    """Run once per fresh DBAPI connection (event listener, not decorator)."""
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    # SQLite defaults to failing instantly when another connection is
    # writing; a desktop app (and the restart test) has overlapping short
    # transactions, so wait up to 5 s instead of raising "database is locked".
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


class Database:
    """Owns the async engine and session factory for one database file."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.engine: AsyncEngine = create_async_engine(async_url(db_path))
        enable_sqlite_pragmas(self.engine.sync_engine)
        self.session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self.engine, expire_on_commit=False
        )

    @asynccontextmanager
    async def new_session(self) -> AsyncIterator[AsyncSession]:
        """Yield a session with commit-on-success / rollback-on-error."""
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except BaseException:
                await session.rollback()
                raise

    async def dispose(self) -> None:
        """Close pooled connections (app shutdown, test teardown)."""
        await self.engine.dispose()
