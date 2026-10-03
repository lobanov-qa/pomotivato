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


@pytest.mark.api
def test_habit_sweep_and_lineage_column_land_on_upgrade(tmp_path):
    """DF7/DF12 hop: legacy habit rows sweep to normal; cloned_from appears."""
    path = tmp_path / "sweep-test.db"
    upgrade_db(path, "7f2a9c41de55")
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO tasks (id, title, type, important, urgent, status,"
            " estimate_blocks, recurrence_json, created_at)"
            " VALUES ('legacy', 'Old habit', 'habit', 0, 0, 'backlog', 1, '{}',"
            " '2026-09-01T00:00:00+00:00')"
        )

    upgrade_db(path, HEAD)

    with sqlite3.connect(path) as connection:
        swept = connection.execute("SELECT type FROM tasks WHERE id='legacy'").fetchone()[0]
        columns = {row[1] for row in connection.execute("PRAGMA table_info(tasks)").fetchall()}
    assert swept == "normal"
    assert "cloned_from" in columns


@pytest.mark.api
def test_no_timer_column_defaults_false_for_existing_rows(tmp_path):
    """DF13 hop: old databases load every pre-existing card as timer work."""
    path = tmp_path / "no-timer-test.db"
    upgrade_db(path, "8e5c31d7b9f4")
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO tasks (id, title, type, important, urgent, status,"
            " estimate_blocks, recurrence_json, created_at)"
            " VALUES ('old', 'Was a timer task', 'normal', 0, 0, 'backlog', 1, '{}',"
            " '2026-09-01T00:00:00+00:00')"
        )

    upgrade_db(path, HEAD)

    with sqlite3.connect(path) as connection:
        flag = connection.execute("SELECT no_timer FROM tasks WHERE id='old'").fetchone()[0]

    assert flag == 0


@pytest.mark.api
def test_sprint_id_link_and_fk_land_with_the_column(tmp_path):
    """E4c hop: existing rows stay NULL (the shelf), the FK is enforced."""
    path = tmp_path / "sprint-link-test.db"
    upgrade_db(path, "3c9f80e2d1a7")
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO tasks (id, title, type, important, urgent, status,"
            " estimate_blocks, recurrence_json, created_at, no_timer)"
            " VALUES ('old', 'Pre-E4c card', 'normal', 0, 0, 'backlog', 1, '{}',"
            " '2026-09-01T00:00:00+00:00', 0)"
        )

    upgrade_db(path, HEAD)

    with sqlite3.connect(path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(tasks)").fetchall()}
        linked = connection.execute("SELECT sprint_id FROM tasks WHERE id='old'").fetchone()[0]
        fks = connection.execute("PRAGMA foreign_key_list(tasks)").fetchall()
        # row layout: id, seq, table, from, to, on_update, on_delete, match
        assert ("sprints", "sprint_id", "id") in {tuple(fk[2:5]) for fk in fks}
        # Enforcement is per-connection (the app turns it on in db.py): the
        # probe must ask for it the same way a runtime connection does.
        connection.execute("PRAGMA foreign_keys=ON")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE tasks SET sprint_id='sprint-ghost' WHERE id='old'")
    assert "sprint_id" in columns
    assert linked is None


@pytest.mark.api
def test_carry_choice_check_lands_and_rejects_unknown_fates(tmp_path):
    """E4c PR 2 hop: the fate column arrives with its CHECK ('left','moved')."""
    path = tmp_path / "carry-choice-test.db"
    upgrade_db(path, "5a9c3f71b8e2")
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO tasks (id, title, type, important, urgent, status,"
            " estimate_blocks, recurrence_json, created_at, no_timer)"
            " VALUES ('old', 'Pre-fate card', 'normal', 0, 0, 'backlog', 1, '{}',"
            " '2026-09-01T00:00:00+00:00', 0)"
        )

    upgrade_db(path, HEAD)

    with sqlite3.connect(path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(tasks)").fetchall()}
        fate = connection.execute("SELECT carry_choice FROM tasks WHERE id='old'").fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE tasks SET carry_choice='carried' WHERE id='old'")
        connection.execute("UPDATE tasks SET carry_choice='left' WHERE id='old'")
    assert "carry_choice" in columns
    assert fate is None  # pre-fate rows load undecided, per spec 07 §3.3 p.3


@pytest.mark.api
def test_score_becomes_nullable_without_losing_existing_scores(tmp_path):
    """E4c PR 3 hop (V24): the batch rewrite keeps rows, drops NOT NULL."""
    path = tmp_path / "score-null-test.db"
    upgrade_db(path, "9d41c07be3f8")
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO sessions (id, day_plan_id, state, settings_json)"
            " VALUES ('s-1', 'p-1', 'stopped', '{}')"
        )
        connection.execute(
            "INSERT INTO segments (id, session_id, phase, planned_min, status)"
            " VALUES ('g-1', 's-1', 'work', 25, 'completed')"
        )
        connection.execute("INSERT INTO reviews (segment_id, score) VALUES ('g-1', 4)")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO reviews (segment_id, score) VALUES ('g-2', NULL)")

    upgrade_db(path, HEAD)

    with sqlite3.connect(path) as connection:
        kept = connection.execute("SELECT score FROM reviews WHERE segment_id='g-1'").fetchone()[0]
        connection.execute(
            "INSERT INTO segments (id, session_id, phase, planned_min, status)"
            " VALUES ('g-2', 's-1', 'work', 25, 'completed')"
        )
        connection.execute("INSERT INTO reviews (segment_id, score) VALUES ('g-2', NULL)")
        skipped = connection.execute("SELECT score FROM reviews WHERE segment_id='g-2'").fetchone()[
            0
        ]
    assert kept == 4
    assert skipped is None


@pytest.mark.api
def test_done_at_column_lands_and_roundtrips(tmp_path: Path) -> None:
    """E4c PR 6 hop (V26): the trim clock arrives additive; old rows NULL."""
    path = tmp_path / "done-at-test.db"
    upgrade_db(path, "b7e02c9a4d13")
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO tasks (id, title, type, important, urgent, status,"
            " estimate_blocks, recurrence_json, created_at, no_timer)"
            " VALUES ('old', 'Pre-trim card', 'normal', 0, 0, 'done', 1, '{}',"
            " '2026-09-01T00:00:00+00:00', 0)"
        )

    upgrade_db(path, HEAD)

    with sqlite3.connect(path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(tasks)").fetchall()}
        stamp = connection.execute("SELECT done_at FROM tasks WHERE id='old'").fetchone()[0]
    assert "done_at" in columns
    assert stamp is None  # legacy closings fall back to created_at (spec §4.6)
