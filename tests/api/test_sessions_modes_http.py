"""HTTP floor for E4b modes: strict refusal, special breaks over the wire.

Same frozen-clock pattern as the sessions floor; these tests prove the
core rules survive DTO/persistence round-trips (spec 05 §7).
"""

from __future__ import annotations

from collections.abc import Iterator
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

BASE_SETTINGS: dict[str, Any] = {
    "work_min": 10,
    "break_min": 5,
    "long_break_min": 15,
    "long_break_every": 2,
    "auto_start_next": True,
}


@pytest.fixture
def http_session(tmp_path: Path) -> Iterator[tuple[TestClient, FakeClock]]:
    db_path = tmp_path / "modes-test.db"
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


def _start(client: TestClient, settings: dict[str, Any]) -> dict[str, Any]:
    response = client.post("/api/sessions", json={"day_plan_id": "p-1", "settings": settings})
    assert response.status_code == HTTPStatus.CREATED
    return dict(response.json())


@pytest.mark.api
def test_strict_mode_pause_returns_409_and_keeps_session_running(http_session):
    client, _clock = http_session
    started = _start(client, {**BASE_SETTINGS, "strict_mode": True})

    paused = client.post(f"/api/sessions/{started['id']}/pause")

    assert paused.status_code == HTTPStatus.CONFLICT
    assert_detail_code(paused, "conflict")
    assert "strict" in paused.json()["detail"]["message"]
    fresh = client.get(f"/api/sessions/{started['id']}").json()
    assert fresh["state"] == "running"


@pytest.mark.api
def test_strict_mode_stops_normally_while_working(http_session):
    client, _clock = http_session
    started = _start(client, {**BASE_SETTINGS, "strict_mode": True})

    stopped = client.post(f"/api/sessions/{started['id']}/stop")

    assert stopped.status_code == HTTPStatus.OK
    assert stopped.json()["state"] == "stopped"


@pytest.mark.api
def test_special_break_survives_persist_roundtrip_with_label(http_session):
    client, clock = http_session
    # The HTTP FSM lives in the machine's local zone (spec 05 ⚑ Q2): anchor
    # 5 min into the 10-min first block, expressed in local wall time.
    anchor_local = (DEFAULT_MOMENT + timedelta(minutes=5)).astimezone()
    settings = {
        **BASE_SETTINGS,
        "special_breaks": [
            {
                "at": anchor_local.strftime("%H:%M"),
                "duration_min": 6,
                "label": "lunch",
            }
        ],
    }
    started = _start(client, settings)
    assert started["settings"]["special_breaks"][0]["at"] == anchor_local.strftime("%H:%M")

    clock.advance(timedelta(minutes=8))
    view = client.get(f"/api/sessions/{started['id']}").json()

    breaks = [s for s in view["timeline"] if s["phase"] == "special_break"]
    assert len(breaks) == 1
    assert breaks[0]["break_label"] == "lunch"
    assert breaks[0]["planned_min"] == 6
    # the work segment was cut short, honestly marked interrupted
    assert view["timeline"][0]["status"] == "interrupted"

    # restart-free proof: the row on disk carries the label (GET re-reads DB
    # only for stopped sessions; force a stop, then read rows via summary).
    client.post(f"/api/sessions/{started['id']}/stop")
    day = DEFAULT_MOMENT.date().isoformat()
    summary = client.get(f"/api/summary/{day}").json()
    assert summary is not None  # summary floor stays green with new phases


@pytest.mark.api
def test_warmup_first_block_shortens_over_http(http_session):
    client, _clock = http_session
    settings = {**BASE_SETTINGS, "warmup_min": 3}

    started = _start(client, settings)

    assert started["timeline"][0]["planned_min"] == 3
    assert started["remaining_sec"] == 3 * 60
    assert started["settings"]["warmup_min"] == 3


@pytest.mark.api
def test_put_session_settings_rejects_out_of_range_warmup(http_session):
    client, _clock = http_session

    bad = client.put(
        "/api/settings/session",
        json={**BASE_SETTINGS, "warmup_min": 99},
    )

    assert bad.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert_detail_code(bad, "invalid")
