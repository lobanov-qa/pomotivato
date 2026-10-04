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
from tests.api.schemas_http import put_in_work
from tests.factories.core_models import DEFAULT_MOMENT

FAST = {
    "work_min": 10,
    "break_min": 5,
    "long_break_min": 15,
    "long_break_every": 2,
    "auto_start_next": True,
}

DAY = DEFAULT_MOMENT.date().isoformat()

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
        # E4c PR 9 (A24): aggregates read sprint-owned cards only — the
        # fixture's work happens inside a sprint covering the frozen today.
        sprint = client.post("/api/sprints", json={"start_date": DAY, "end_date": "2026-09-13"})
        assert sprint.status_code == HTTPStatus.CREATED, sprint.text
        sprint_id = sprint.json()["id"]
        client.patch(f"/api/sprints/{sprint_id}", json={"status": "active"})
        client.post(
            "/api/tasks", json={"id": "t-1", "title": "First block", "sprint_id": sprint_id}
        )
        client.post(
            "/api/tasks", json={"id": "t-2", "title": "Second block", "sprint_id": sprint_id}
        )
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
    """Walk the plan cards into «В работе» (V7 funnel) and run the dial."""
    put_in_work(client, "t-1", "t-2")
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
def _active_sprint(client: TestClient) -> str:
    """The fixture's sprint (the first one the list returns)."""
    return str(client.get("/api/sprints").json()[0]["id"])


def test_stats_quadrants_bucket_done_tasks(http_app):
    client, _clock = http_app
    client.post(
        "/api/tasks",
        json={
            "id": "t-9",
            "title": "Urgent and important",
            "important": True,
            "urgent": True,
            "sprint_id": _active_sprint(client),  # A24: aggregate members need an owner
        },
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
    client.post(
        "/api/tasks",
        json={"id": "t-9", "title": "Stuck frog", "sprint_id": _active_sprint(client)},
    )
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
        "missed_days",  # E4c PR 9 (spec 07 §4.5): additive section
    }
    assert keys == set(body)


@pytest.mark.api
def test_aggregates_ignore_shelf_tasks(http_app):
    """A24 (spec 07 §10.13): a sprint-less card is the sandbox — it never
    enters the totals, even when worked."""
    client, _clock = http_app
    client.post("/api/tasks", json={"id": "t-shelf", "title": "Sandbox card"})
    client.post(
        "/api/tasks",
        json={"id": "t-owned", "title": "Sprint card", "sprint_id": _active_sprint(client)},
    )

    body = client.get("/api/stats", params=PERIOD).json()

    # t-1, t-2, t-owned count; t-shelf is invisible to every aggregate.
    assert body["totals"]["tasks_total"] == 3


@pytest.mark.api
def test_missed_days_counts_unworked_past_ticks(http_app):
    """Spec 07 §4.5: a sprint card's past tick without a completed block
    is a missed day; today is never a miss (the day may still be worked)."""
    client, clock = http_app
    sprint_id = _active_sprint(client)  # 2026-09-03 .. 2026-09-13
    client.post(
        "/api/tasks",
        json={
            "id": "t-late",
            "title": "Procrastinated",
            "sprint_id": sprint_id,
            "recurrence": {"kind": "on_dates", "days": ["2026-09-05", "2026-09-06"]},
        },
    )
    clock.advance(timedelta(days=5))  # now 2026-09-08: both ticks are past

    body = client.get("/api/stats", params={"from": "2026-09-03", "to": "2026-09-08"}).json()

    assert body["missed_days"] == {"count": 2, "cards": 1}


@pytest.mark.api
def test_missed_days_excludes_the_shelf(http_app):
    """A24/§4.5: a shelf card with past ticks never enters the metric."""
    client, clock = http_app
    client.post(
        "/api/tasks",
        json={
            "id": "t-shelf-tick",
            "title": "Sandbox with marks",
            "recurrence": {"kind": "on_dates", "days": ["2026-09-05"]},
        },
    )  # shelf card: its ticks are nobody's metric
    clock.advance(timedelta(days=5))

    body = client.get("/api/stats", params={"from": "2026-09-03", "to": "2026-09-08"}).json()

    assert body["missed_days"] == {"count": 0, "cards": 0}
