"""HTTP floor for GET /api/week (spec 04 §4.2).

FakeClock owns "today"; the default window is Monday of the current ISO
week, so days are located by date, not by index. Recurrence expansion for
future days is checked against real core logic, not mocked.
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


@pytest.fixture
def http_app(tmp_path: Path) -> Iterator[tuple[TestClient, FakeClock]]:
    """Client over temp DB with one slotted day and a daily habit task."""
    app = create_app(tmp_path / "week-test.db")
    clock = FakeClock(DEFAULT_MOMENT)
    app.state.clock = clock
    with TestClient(app) as client:
        client.post("/api/tasks", json={"id": "t-1", "title": "Work task"})
        client.post(
            "/api/tasks",
            json={"id": "h-1", "title": "Daily habit", "recurrence": {"kind": "daily"}},
        )
        client.put(
            f"/api/day-plans/{DAY}",
            json={"id": "p-1", "date": DAY, "slots": [{"sector": 1, "task_id": "t-1"}]},
        )
        yield client, clock


def _start(client: TestClient) -> dict[str, Any]:
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
def test_week_validates_days_range_and_bad_start(http_app):
    client, _clock = http_app

    zero_days = client.get("/api/week", params={"days": "0"})
    huge_days = client.get("/api/week", params={"days": "15"})
    bad_start = client.get("/api/week", params={"start": "not-a-date"})

    assert zero_days.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert huge_days.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert bad_start.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
