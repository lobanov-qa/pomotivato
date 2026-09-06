"""HTTP floor for sessions/reviews: FSM lifecycle on a frozen clock.

FakeClock is the only time source: "25 minutes in 0 seconds" per spec 01
§3, no sleeps. A restart test builds a SECOND app over the same file (the
registry is per-process; the DB row is the witness of the Q4 sweep).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from datetime import timedelta
from http import HTTPStatus
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from pomotivato.core.clock import FakeClock
from pomotivato.main import create_app
from tests.api.schemas_http import assert_detail_code
from tests.factories.core_models import DEFAULT_MOMENT

FAST = {
    "work_min": 10,
    "break_min": 5,
    "long_break_min": 15,
    "long_break_every": 2,
    "auto_start_next": True,
}


@pytest.fixture
def http_session(tmp_path: Path) -> Iterator[tuple[TestClient, FakeClock]]:
    """Client over temp DB + frozen clock + a two-slot plan ready to run."""
    db_path = tmp_path / "sessions-test.db"
    app = create_app(db_path)
    clock = FakeClock(DEFAULT_MOMENT)
    app.state.clock = clock
    with TestClient(app) as client:
        client.post("/api/tasks", json={"id": "t-1", "title": "First block"})
        client.post("/api/tasks", json={"id": "t-2", "title": "Second block"})
        plan = {
            "id": "p-1",
            "date": DEFAULT_MOMENT.date().isoformat(),
            "slots": [{"sector": 1, "task_id": "t-1"}, {"sector": 2, "task_id": "t-2"}],
        }
        client.put(f"/api/day-plans/{plan['date']}", json=plan)
        yield client, clock
    # Second create_app for restart tests shares the same path via closure.


def _start(client: TestClient, settings: Mapping[str, object] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"day_plan_id": "p-1"}
    if settings:
        body["settings"] = dict(settings)
    response = client.post("/api/sessions", json=body)
    assert response.status_code == HTTPStatus.CREATED
    return dict(response.json())


@pytest.mark.api
def test_start_returns_running_work_when_plan_has_slots(http_session):
    client, _clock = http_session

    view = _start(client, FAST)

    assert view["state"] == "running"
    assert view["phase"] == "work"
    assert view["remaining_sec"] == 10 * 60
    assert view["id"].startswith("session-")
    assert view["timeline"][0]["task_id"] == "t-1"


@pytest.mark.api
def test_get_exposes_frozen_slots_snapshot_when_session_started(http_session):
    """Dial sectors come from the snapshot, not the live plan (spec 03 §3)."""
    client, _clock = http_session

    started = _start(client, FAST)
    client.put(
        f"/api/day-plans/{DEFAULT_MOMENT.date().isoformat()}",
        json={
            "id": "p-1",
            "date": DEFAULT_MOMENT.date().isoformat(),
            "slots": [{"sector": 1, "task_id": "t-2"}],
        },
    )

    view = client.get(f"/api/sessions/{started['id']}").json()

    assert [slot["task_id"] for slot in view["slots"]] == ["t-1", "t-2"]


@pytest.mark.api
def test_start_404s_when_day_plan_missing(http_session):
    client, _clock = http_session

    response = client.post("/api/sessions", json={"day_plan_id": "ghost"})

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert_detail_code(response, "not_found")


@pytest.mark.api
def test_pause_freezes_remaining_when_clock_keeps_running(http_session):
    client, clock = http_session
    session_id = _start(client, FAST)["id"]

    clock.advance(timedelta(minutes=2))
    paused = client.post(f"/api/sessions/{session_id}/pause").json()
    clock.advance(timedelta(minutes=7))
    still = client.get(f"/api/sessions/{session_id}").json()
    resumed = client.post(f"/api/sessions/{session_id}/resume")

    assert paused["remaining_sec"] == 8 * 60
    assert still["state"] == "paused"
    assert still["remaining_sec"] == 8 * 60  # wall time must not burn
    assert resumed.json()["remaining_sec"] == 8 * 60


@pytest.mark.api
def test_advance_flows_work_break_work_when_deadline_passed(http_session):
    client, clock = http_session
    session_id = _start(client, FAST)["id"]

    clock.advance(timedelta(minutes=10))
    view = client.get(f"/api/sessions/{session_id}").json()

    assert view["phase"] == "break"
    assert view["remaining_sec"] == 5 * 60
    assert view["timeline"][0]["status"] == "completed"


@pytest.mark.api
def test_review_accepted_when_work_completed(http_session):
    client, clock = http_session
    session_id = _start(client, FAST)["id"]
    clock.advance(timedelta(minutes=10))
    segment_id = client.get(f"/api/sessions/{session_id}").json()["timeline"][0]["id"]

    created = client.post("/api/reviews", json={"segment_id": segment_id, "score": 4})
    again = client.post("/api/reviews", json={"segment_id": segment_id, "score": 5})

    assert created.status_code == HTTPStatus.CREATED
    assert again.status_code == HTTPStatus.CONFLICT  # T17: one review per segment

    # V4 must be a 422, not a 409: probe on a fresh completed segment.
    clock.advance(timedelta(minutes=15))  # break + second work elapse
    timeline = client.get(f"/api/sessions/{session_id}").json()["timeline"]
    second_work = [s for s in timeline if s["phase"] == "work"][-1]["id"]
    bad = client.post("/api/reviews", json={"segment_id": second_work, "score": 9})

    assert bad.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert_detail_code(bad, "invalid")
    view = client.get(f"/api/sessions/{session_id}").json()
    assert view["average_score"] == 4.0


@pytest.mark.api
def test_study_review_advances_repetition_queue_when_due(http_session, tmp_path):
    client, clock = http_session
    client.post("/api/tasks", json={"id": "t-study", "title": "Learn", "type": "study"})
    plan = {
        "id": "p-study",
        "date": DEFAULT_MOMENT.date().isoformat(),
        "slots": [{"sector": 1, "task_id": "t-study"}],
    }
    client.put(f"/api/day-plans/{plan['date']}", json=plan)
    view = _start(client, FAST)
    clock.advance(timedelta(minutes=10))
    session_id = view["id"]
    segment_id = client.get(f"/api/sessions/{session_id}").json()["timeline"][0]["id"]

    response = client.post("/api/reviews", json={"segment_id": segment_id, "score": 5})

    assert response.status_code == HTTPStatus.CREATED
    import sqlite3

    with sqlite3.connect(tmp_path / "sessions-test.db") as connection:
        row = connection.execute(
            "SELECT interval_idx, next_due FROM repetitions WHERE task_id='t-study'"
        ).fetchone()

    # Ladder owned by core science.py: first review steps 0->1, due +3 days.
    assert row is not None and row[0] == 1
    assert row[1] == (DEFAULT_MOMENT.date() + timedelta(days=3)).isoformat()


@pytest.mark.api
def test_stop_interrupts_open_segment_and_frees_registry(http_session):
    client, _clock = http_session
    session_id = _start(client, FAST)["id"]

    stopped = client.post(f"/api/sessions/{session_id}/stop")

    body = stopped.json()
    assert stopped.status_code == HTTPStatus.OK
    assert body["state"] == "stopped"
    assert body["timeline"][-1]["status"] == "interrupted"
    resume_after = client.post(f"/api/sessions/{session_id}/resume")
    assert resume_after.status_code == HTTPStatus.CONFLICT


@pytest.mark.api
def test_restart_restores_live_session_when_clock_shared(http_session, tmp_path):
    client, clock = http_session
    session_id = _start(client, FAST)["id"]
    clock.advance(timedelta(minutes=3))

    # Same database file + same time = a process restart at the same moment.
    restarted = create_app(tmp_path / "sessions-test.db")
    restarted.state.clock = clock
    with TestClient(restarted) as fresh:
        view = fresh.get(f"/api/sessions/{session_id}").json()
        status = fresh.get("/api/status").json()
        command = fresh.post(f"/api/sessions/{session_id}/pause")

    assert view["state"] == "running"
    assert view["remaining_sec"] == 7 * 60
    assert status["active"] is True
    assert status["session_id"] == session_id
    assert command.status_code == HTTPStatus.OK


@pytest.mark.api
def test_restart_catches_overdue_phase_without_time_refund(http_session, tmp_path):
    client, clock = http_session
    session_id = _start(client, FAST)["id"]
    clock.advance(timedelta(minutes=12))  # work (10) is overdue by 2

    restarted = create_app(tmp_path / "sessions-test.db")
    restarted.state.clock = clock
    with TestClient(restarted) as fresh:
        view = fresh.get(f"/api/sessions/{session_id}").json()

    # Honest catch-up: work closed at its ORIGINAL deadline, break started
    # from there — the 2 wasted minutes are neither refunded nor charged.
    assert view["state"] == "running"
    assert view["phase"] == "break"
    assert view["remaining_sec"] == 3 * 60
    assert view["timeline"][0]["status"] == "completed"


@pytest.mark.api
def test_restart_sweeps_legacy_rows_without_snapshot(http_session, tmp_path):
    import sqlite3

    client, clock = http_session
    session_id = _start(client, FAST)["id"]
    db_file = tmp_path / "sessions-test.db"
    with sqlite3.connect(db_file) as conn:  # simulate a pre-E3 row
        conn.execute("UPDATE sessions SET slots_json = NULL")

    restarted = create_app(db_file)
    restarted.state.clock = clock
    with TestClient(restarted) as fresh:
        view = fresh.get(f"/api/sessions/{session_id}").json()
        command = fresh.post(f"/api/sessions/{session_id}/pause")

    assert view["state"] == "stopped"
    assert view["stop_reason"] == "server_restart"
    assert view["timeline"][0]["status"] == "interrupted"
    assert command.status_code == HTTPStatus.CONFLICT


@pytest.mark.api
def test_paused_session_survives_restart_frozen(http_session, tmp_path):
    client, clock = http_session
    session_id = _start(client, FAST)["id"]
    clock.advance(timedelta(minutes=2))
    client.post(f"/api/sessions/{session_id}/pause")
    clock.advance(timedelta(minutes=20))  # wall time burns during downtime

    restarted = create_app(tmp_path / "sessions-test.db")
    restarted.state.clock = clock
    with TestClient(restarted) as fresh:
        view = fresh.get(f"/api/sessions/{session_id}").json()
        resumed = fresh.post(f"/api/sessions/{session_id}/resume")

    assert view["state"] == "paused"
    assert view["remaining_sec"] == 8 * 60  # pause does not burn
    assert resumed.json()["remaining_sec"] == 8 * 60


@pytest.mark.api
def test_commands_404_when_session_never_existed(http_session):
    client, _clock = http_session

    response = client.post("/api/sessions/ghost/pause")

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert_detail_code(response, "not_found")
