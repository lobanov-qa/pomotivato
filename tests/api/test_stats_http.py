"""HTTP floor for GET /api/stats (spec 04 §4/§8).

FakeClock is the only time source; blocks are played with FAST settings so
the arithmetic (ratio, heatmap, zombie threshold) is what fails, not setup.
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

PERIOD = {
    "from": DEFAULT_MOMENT.date().isoformat(),
    "to": DEFAULT_MOMENT.date().isoformat(),
}


@pytest.fixture
def http_app(tmp_path: Path) -> Iterator[tuple[TestClient, FakeClock]]:
    """Client over temp DB + frozen clock + two plan slots ready to run."""
    app = create_app(tmp_path / "stats-test.db")
    clock = FakeClock(DEFAULT_MOMENT)
    app.state.clock = clock
    with TestClient(app) as client:
        client.post("/api/tasks", json={"id": "t-1", "title": "First block"})
        client.post("/api/tasks", json={"id": "t-2", "title": "Second block"})
        day = DEFAULT_MOMENT.date().isoformat()
        client.put(
            f"/api/day-plans/{day}",
            json={
                "id": "p-1",
                "date": day,
                "slots": [{"sector": 1, "task_id": "t-1"}, {"sector": 2, "task_id": "t-2"}],
            },
        )
        yield client, clock


def _start(client: TestClient) -> dict[str, Any]:
    response = client.post("/api/sessions", json={"day_plan_id": "p-1", "settings": FAST})
    assert response.status_code == HTTPStatus.CREATED
    return dict(response.json())


def _finish_first_block(client: TestClient, clock: FakeClock, session_id: str) -> str:
    """Let the first work segment elapse and return its segment id."""
    clock.advance(timedelta(minutes=10))
    timeline = client.get(f"/api/sessions/{session_id}").json()["timeline"]
    return str(timeline[0]["id"])


@pytest.mark.api
def test_stats_answers_zeros_when_nothing_was_recorded(http_app):
    client, _clock = http_app

    body = client.get("/api/stats", params=PERIOD).json()

    assert body["period"] == PERIOD
    assert body["totals"] == {
        "blocks_done": 0,
        "focus_min": 0,
        "average_score": None,
        "reviews_count": 0,
        "tasks_done": 0,
        "tasks_total": 2,
    }
    assert body["heatmap"] == []
    assert body["streak"] == {
        "current": 0,
        "current_started": None,
        "record": 0,
        "record_started": None,
    }


@pytest.mark.api
def test_stats_reports_blocks_scores_and_heatmap_after_completed_work(http_app):
    client, clock = http_app
    session_id = _start(client)["id"]
    segment_id = _finish_first_block(client, clock, session_id)
    client.post("/api/reviews", json={"segment_id": segment_id, "score": 4})
    client.post(f"/api/sessions/{session_id}/stop")

    body = client.get("/api/stats", params=PERIOD).json()

    assert body["totals"]["blocks_done"] == 1
    assert body["totals"]["focus_min"] == 10
    assert body["totals"]["average_score"] == 4.0
    assert body["heatmap"] == [
        {"date": DEFAULT_MOMENT.date().isoformat(), "blocks_done": 1, "focus_min": 10},
    ]
    assert body["streak"]["current"] == 1


@pytest.mark.api
def test_stats_estimate_vs_fact_uses_finished_blocks_over_estimate(http_app):
    client, clock = http_app
    session_id = _start(client)["id"]
    _finish_first_block(client, clock, session_id)
    client.post("/api/tasks/t-1/status", json={"to": "planned"})
    client.post("/api/tasks/t-1/status", json={"to": "doing"})
    client.post("/api/tasks/t-1/status", json={"to": "done"})

    body = client.get("/api/stats", params=PERIOD).json()

    ratio = body["estimate_vs_fact"]
    assert ratio["points"] == [
        {"task_id": "t-1", "title": "First block", "estimate": 1, "actual": 1}
    ]
    assert ratio["ratio"] == 1.0


@pytest.mark.api
def test_stats_quadrants_bucket_done_tasks(http_app):
    client, _clock = http_app
    client.post(
        "/api/tasks",
        json={"id": "t-9", "title": "Urgent and important", "important": True, "urgent": True},
    )
    client.post("/api/tasks/t-9/status", json={"to": "planned"})
    client.post("/api/tasks/t-9/status", json={"to": "doing"})
    client.post("/api/tasks/t-9/status", json={"to": "done"})

    body = client.get("/api/stats", params=PERIOD).json()

    by_key = {row["key"]: row for row in body["quadrants"]}
    assert by_key["important_urgent"]["tasks_done"] == 1
    assert by_key["neither"]["tasks_done"] == 0


@pytest.mark.api
def test_stats_zombies_flag_doing_task_without_recent_blocks(http_app):
    client, clock = http_app
    client.post("/api/tasks", json={"id": "t-9", "title": "Stuck frog"})
    client.post("/api/tasks/t-9/status", json={"to": "planned"})
    client.post("/api/tasks/t-9/status", json={"to": "doing"})
    clock.advance(timedelta(days=10))

    body = client.get("/api/stats").json()

    assert body["zombies"]["count"] == 1
    assert body["zombies"]["items"] == [{"task_id": "t-9", "title": "Stuck frog", "days_stuck": 10}]


@pytest.mark.api
def test_stats_zombies_ignore_task_with_a_recent_block(http_app):
    client, clock = http_app
    client.post("/api/tasks/t-1/status", json={"to": "planned"})
    client.post("/api/tasks/t-1/status", json={"to": "doing"})
    session_id = _start(client)["id"]
    _finish_first_block(client, clock, session_id)  # fresh block today

    body = client.get("/api/stats").json()

    assert body["zombies"]["count"] == 0


@pytest.mark.api
def test_stats_period_validation_rejects_reversed_and_long_ranges(http_app):
    client, _clock = http_app
    day_a = "2026-09-01"
    day_b = "2026-09-05"

    reversed_range = client.get("/api/stats", params={"from": day_b, "to": day_a})
    too_long = client.get("/api/stats", params={"from": "2020-01-01", "to": "2026-01-01"})
    defaults = client.get("/api/stats")

    assert reversed_range.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert reversed_range.json()["detail"]["code"] == "invalid"
    assert too_long.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert defaults.status_code == HTTPStatus.OK


@pytest.mark.api
def test_stats_snapshot_matches_dto_contract(http_app):
    client, _clock = http_app

    body = client.get("/api/stats", params=PERIOD).json()

    keys = {
        "period",
        "totals",
        "heatmap",
        "streak",
        "estimate_vs_fact",
        "quadrants",
        "goal_depth",
        "parents",
        "zombies",
    }
    assert keys == set(body)
