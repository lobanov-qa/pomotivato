"""Fixtures for the API/service integration floor: real temp SQLite per test."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest

from pomotivato.core.clock import FakeClock
from pomotivato.infra.db import Database
from pomotivato.infra.migrations import upgrade_db
from pomotivato.services.day_plan_service import DayPlanService
from pomotivato.services.settings_service import SettingsService
from pomotivato.services.task_service import TaskService
from tests.factories.core_models import DEFAULT_MOMENT


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    """A migrated file-based SQLite (same up-migration as app lifespan)."""
    path = tmp_path / "api-test.db"
    upgrade_db(path)
    database = Database(path)
    yield database
    # Scenarios run their own event loops; without an explicit dispose the
    # pooled aiosqlite threads die at GC time and pytest reports it as an
    # unhandled thread exception. A throwaway loop is enough to close them.
    asyncio.run(database.dispose())


@dataclass
class Services:
    """Service layer bundle; every call runs in its own transaction."""

    task: TaskService
    day_plan: DayPlanService
    settings: SettingsService
    clock: FakeClock


@pytest.fixture
def call(database: Database) -> Callable[[], AbstractAsyncContextManager[Services]]:
    """Async context factory: `async with call() as svc:` == one request."""

    @asynccontextmanager
    async def _open() -> AsyncIterator[Services]:
        async with database.new_session() as session:
            yield Services(
                task=TaskService(session),
                day_plan=DayPlanService(session),
                settings=SettingsService(session),
                clock=FakeClock(DEFAULT_MOMENT),
            )

    return _open
