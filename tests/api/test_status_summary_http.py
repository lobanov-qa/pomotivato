"""HTTP floor for GET /api/status and GET /api/summary/{date} (spec 03 §9).

FakeClock is the only time source; summary numbers are checked against
FAST-length blocks so the arithmetic itself is under test.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from http import HTTPStatus
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from pomotivato.api.schemas import DailySummaryDto, StatusDto
from pomotivato.core.clock import FakeClock
from pomotivato.main import create_app
from tests.api.schemas_http import validate_as
from tests.factories.core_models import DEFAULT_MOMENT

FAST = {
    "work_min": 10,
    "break_min": 5,
    "long_break_min": 15,
    "long_break_every": 2,
    "auto_start_next": True,
}


@pytest.fixture
def http_app(tmp_path: Path) -> Iterator[tuple[TestClient, FakeClock]]:
    """Client over temp DB + frozen clock + a two-slot plan ready to run."""
    app = create_app(tmp_path / "status-test.db")
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


def _start(client: TestClient) -> dict[str, Any]:
    response = client.post("/api/sessions", json={"day_plan_id": "p-1", "settings": FAST})
    assert response.status_code == HTTPStatus.CREATED
    return dict(response.json())


@pytest.mark.api
def test_status_reports_inactive_when_no_session_exists(http_app):
    client, clock = http_app

    body = client.get("/api/status").json()

    validate_as(StatusDto, body)
    assert body["active"] is False
    assert body["session_id"] is None
    assert body["server_now"] == clock.now().isoformat()


@pytest.mark.api
def test_status_reports_phase_and_remaining_when_session_running(http_app):
    client, clock = http_app
    session_id = _start(client)["id"]

    clock.advance(timedelta(minutes=3))
    body = client.get("/api/status").json()

    validate_as(StatusDto, body)
    assert body["active"] is True
    assert body["session_id"] == session_id
    assert body["state"] == "running"
    assert body["phase"] == "work"
    assert body["remaining_sec"] == 7 * 60


@pytest.mark.api
def test_status_goes_inactive_when_session_stopped(http_app):
    client, _clock = http_app
    session_id = _start(client)["id"]

    client.post(f"/api/sessions/{session_id}/stop")
    body = client.get("/api/status").json()

    assert body["active"] is False
    assert body["date"] == DEFAULT_MOMENT.date().isoformat()


@pytest.mark.api
def test_summary_reports_planned_only_when_day_plan_exists(http_app):
    client, _clock = http_app
    day = DEFAULT_MOMENT.date().isoformat()

    before = client.get(f"/api/summary/{day}").json()
    empty = client.get("/api/summary/2000-01-01").json()

    validate_as(DailySummaryDto, before)
    assert before["blocks_planned"] == 2
    assert before["blocks_done"] == 0
    assert empty["blocks_planned"] == 0
    assert empty["average_score"] is None


@pytest.mark.api
def test_summary_counts_completed_blocks_and_reviews(http_app):
    client, clock = http_app
    day = DEFAULT_MOMENT.date().isoformat()
    session_id = _start(client)["id"]

    clock.advance(timedelta(minutes=10))  # first work block elapses
    segment_id = client.get(f"/api/sessions/{session_id}").json()["timeline"][0]["id"]
    client.post("/api/reviews", json={"segment_id": segment_id, "score": 4})
    client.post(f"/api/sessions/{session_id}/stop")
    body = client.get(f"/api/summary/{day}").json()

    validate_as(DailySummaryDto, body)
    assert body["blocks_done"] == 1
    assert body["focus_min"] == 10
    assert body["reviews_count"] == 1
    assert body["average_score"] == 4.0
    assert body["tasks_done"] == 1


@pytest.mark.api
def test_summary_averages_reviews_and_ignores_breaks_when_two_blocks_done(http_app):
    client, clock = http_app
    day = DEFAULT_MOMENT.date().isoformat()
    session_id = _start(client)["id"]

    clock.advance(timedelta(minutes=10))  # first work over, break runs on
    timeline = client.get(f"/api/sessions/{session_id}").json()["timeline"]
    first_work = timeline[0]["id"]
    clock.advance(timedelta(minutes=15))  # break + second work elapse
    timeline = client.get(f"/api/sessions/{session_id}").json()["timeline"]
    second_work = [s for s in timeline if s["phase"] == "work"][-1]["id"]
    client.post("/api/reviews", json={"segment_id": first_work, "score": 4})
    client.post("/api/reviews", json={"segment_id": second_work, "score": 5})
    body = client.get(f"/api/summary/{day}").json()

    assert body["blocks_done"] == 2
    assert body["focus_min"] == 20  # two 10-min works, the 5-min break is not focus
    assert body["average_score"] == 4.5
    assert body["tasks_done"] == 2  # two different tasks from the plan slots
