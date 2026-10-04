"""HTTP floor for GET /api/week (spec 04 §4.2).

FakeClock owns "today"; the default window is Monday of the current ISO
week, so days are located by date, not by index. Recurrence expansion for
future days is checked against real core logic, not mocked.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
from http import HTTPStatus
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from pomotivato.core.clock import FakeClock
from pomotivato.main import create_app
from tests.api.schemas_http import put_in_work
from tests.factories.core_models import DEFAULT_MOMENT

FAST = {
    "work_min": 10,
    "break_min": 5,
    "long_break_min": 15,
    "long_break_every": 2,
    "auto_start_next": True,
}
DAY = DEFAULT_MOMENT.date().isoformat()  # 2026-09-03, Thursday
MONDAY = (DEFAULT_MOMENT - timedelta(days=3)).date().isoformat()  # week start
MONDAY_ISO = date.fromisoformat(MONDAY)


@pytest.fixture
def http_app(tmp_path: Path) -> Iterator[tuple[TestClient, FakeClock]]:
    """Client over temp DB with one slotted day and a daily habit task.

    E4c PR 9 (A24): the sprint screen shows sprint-bound rows only, so the
    fixture's cards live in a sprint covering the window.
    """
    app = create_app(tmp_path / "week-test.db")
    clock = FakeClock(DEFAULT_MOMENT)
    app.state.clock = clock
    with TestClient(app) as client:
        # Sprints may not start in the past (V19), so the window opens
        # today; Once/Daily cards are period-agnostic (V19 checks OnDates
        # only) and the screen filter cares about the OWNER, not dates.
        sprint = client.post("/api/sprints", json={"start_date": DAY, "end_date": "2026-09-13"})
        assert sprint.status_code == HTTPStatus.CREATED, sprint.text
        sprint_id = sprint.json()["id"]
        client.patch(f"/api/sprints/{sprint_id}", json={"status": "active"})
        client.post("/api/tasks", json={"id": "t-1", "title": "Work task", "sprint_id": sprint_id})
        client.post(
            "/api/tasks",
            json={
                "id": "h-1",
                "title": "Daily habit",
                "recurrence": {"kind": "daily"},
                "sprint_id": sprint_id,
            },
        )
        client.put(
            f"/api/day-plans/{DAY}",
            json={"id": "p-1", "date": DAY, "slots": [{"sector": 1, "task_id": "t-1"}]},
        )
        yield client, clock


def _start(client: TestClient) -> dict[str, Any]:
    """Walk the plan card into «В работе» (V7 funnel) and run the dial."""
    put_in_work(client, "t-1")
    response = client.post("/api/sessions", json={"day_plan_id": "p-1", "settings": FAST})
    assert response.status_code == HTTPStatus.CREATED
    return dict(response.json())


def _items(client: TestClient, **params: str) -> list[dict[str, Any]]:
    response = client.get("/api/week", params=params or None)
    assert response.status_code == HTTPStatus.OK
    return list(response.json()["items"])


def _day(items: list[dict[str, Any]], date_str: str) -> dict[str, Any]:
    return next(item for item in items if item["date"] == date_str)


@pytest.mark.api
def test_week_defaults_to_seven_days_from_monday_of_current_week(http_app):
    client, _clock = http_app

    items = _items(client)

    assert len(items) == 7
    assert items[0]["date"] == MONDAY
    assert items[-1]["date"] == (DEFAULT_MOMENT + timedelta(days=3)).date().isoformat()


@pytest.mark.api
def test_week_past_day_shows_planned_slot_and_empty_summary(http_app):
    client, _clock = http_app

    day = _day(_items(client), DAY)

    assert day["kind"] == "past"
    assert day["slots"] == [
        {
            "sector": 1,
            "task_id": "t-1",
            "task_title": "Work task",
            "status": "backlog",
            "last_score": None,
        }
    ]
    assert day["summary"]["blocks_done"] == 0


@pytest.mark.api
def test_week_past_day_reflects_completed_blocks_after_real_session(http_app):
    client, clock = http_app
    session_id = _start(client)["id"]
    clock.advance(timedelta(minutes=10))
    segment_id = client.get(f"/api/sessions/{session_id}").json()["timeline"][0]["id"]
    client.post("/api/reviews", json={"segment_id": segment_id, "score": 5})
    client.post(f"/api/sessions/{session_id}/stop")

    day = _day(_items(client), DAY)

    assert day["summary"] == {
        "blocks_done": 1,
        "focus_min": 10,
        "average_score": 5.0,
        "tasks_done": 1,
    }
    assert day["slots"][0]["last_score"] == 5
    assert day["volume"] == 1


@pytest.mark.api
def test_week_future_days_materialize_daily_recurrence(http_app):
    client, _clock = http_app

    items = _items(client)
    friday = _day(items, (DEFAULT_MOMENT + timedelta(days=1)).date().isoformat())

    assert friday["kind"] == "future"
    assert friday["planned"] == [{"task_id": "h-1", "title": "Daily habit", "type": "normal"}]
    assert friday["volume"] == 1
    # StatusDto precedent: kind is the discriminator, not key presence —
    # a past day answers planned: null (spec 04 §4.2).
    assert _day(items, DAY)["planned"] is None
    assert friday["summary"] is None


@pytest.mark.api
def test_week_future_day_shows_added_slot_and_no_ghost(http_app):
    """Spec 05 §3.8 (E4c §9: via add, the activate endpoint is gone): after
    the card lands in the plan, the week reads a real slot, not a ghost."""
    client, clock = http_app
    tomorrow = (clock.now().date() + timedelta(days=1)).isoformat()

    added = client.post(f"/api/day-plans/{tomorrow}/add", json={"task_id": "h-1"})

    assert added.status_code == HTTPStatus.OK
    assert added.json()["added"]  # "h-1" lands on sector 1
    friday = _day(_items(client), tomorrow)
    assert [s["task_id"] for s in friday["slots"]] == ["h-1"]
    assert friday["planned"] == []  # the preview stopped ghosting it
    assert friday["volume"] == 1


@pytest.mark.api
def test_week_validates_days_range_and_bad_start(http_app):
    client, _clock = http_app

    zero_days = client.get("/api/week", params={"days": "0"})
    huge_days = client.get("/api/week", params={"days": "15"})
    bad_start = client.get("/api/week", params={"start": "not-a-date"})

    assert zero_days.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert huge_days.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert bad_start.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.api
def test_week_screen_hides_shelf_tasks_when_sprint_exists(http_app):
    """A24 (spec 07 §4.1.2): a daily card WITHOUT a sprint never appears on
    the sprint screen — planned rows and slot rows are sprint-bound."""
    client, _clock = http_app
    client.post(
        "/api/tasks",
        json={"id": "s-1", "title": "Shelf habit", "recurrence": {"kind": "daily"}},
    )
    friday = (MONDAY_ISO + timedelta(days=4)).isoformat()

    items = client.get("/api/week", params={"start": MONDAY_ISO, "days": 7}).json()["items"]
    planned = [row["task_id"] for row in _day(items, friday)["planned"]]

    assert "h-1" in planned  # the sprint-owned daily habit still shows
    assert "s-1" not in planned
