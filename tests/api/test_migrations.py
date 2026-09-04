"""Migration floor: the schema must roll forward, back and up again (DoD E2)."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from pomotivato.infra.migrations import BASE, HEAD, upgrade_db
from pomotivato.infra.orm import Base
from pomotivato.main import create_app

TABLES = {table.name for table in Base.metadata.sorted_tables}


def _existing_tables(path: Path) -> set[str]:
    with sqlite3.connect(path) as connection:
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {row[0] for row in rows}


@pytest.mark.api
def test_schema_roundtrip_survives_downgrade_to_base(tmp_path):
    path = tmp_path / "pomotivato-test.db"

    upgrade_db(path, HEAD)
    assert _existing_tables(path) >= TABLES

    upgrade_db(path, BASE)
    assert TABLES.isdisjoint(_existing_tables(path))

    upgrade_db(path, HEAD)
    assert _existing_tables(path) >= TABLES


@pytest.mark.api
def test_app_startup_migrates_schema_and_serves_health(tmp_path):
    path = tmp_path / "pomotivato-test.db"
    app = create_app(path)

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert _existing_tables(path) >= TABLES


@pytest.mark.api
def test_foreign_keys_and_wal_enabled_on_runtime_connections(tmp_path):
    path = tmp_path / "pomotivato-test.db"
    app = create_app(path)

    async def probe() -> tuple[str, int]:
        db = app.state.db
        async with db.new_session() as session:
            journal = (await session.execute(text("PRAGMA journal_mode"))).scalar_one()
            foreign_keys = (await session.execute(text("PRAGMA foreign_keys"))).scalar_one()
        await db.dispose()
        return str(journal), int(foreign_keys)

    journal, foreign_keys = asyncio.run(probe())

    assert journal == "wal"
    assert foreign_keys == 1
