"""HTTP floor for spec 05 E4b science endpoints: add/activate, hints, due."""

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
from tests.api.schemas_http import assert_detail_code
from tests.factories.core_models import DEFAULT_MOMENT

TODAY = DEFAULT_MOMENT.date()  # frozen clock: the server's "today" is this

FAST: dict[str, Any] = {
    "work_min": 10,
    "break_min": 5,
    "long_break_min": 15,
    "long_break_every": 2,
    "auto_start_next": True,
}


@pytest.fixture
def http_client(tmp_path: Path) -> Iterator[tuple[TestClient, FakeClock]]:
    app = create_app(tmp_path / "science-test.db")
    clock = FakeClock(DEFAULT_MOMENT)
    app.state.clock = clock
    with TestClient(app) as client:
        yield client, clock


def make_task(client: TestClient, task_id: str, **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"id": task_id, "title": f"Task {task_id}"}
    body.update(extra)
    response = client.post("/api/tasks", json=body)
    assert response.status_code == HTTPStatus.CREATED, response.text
    return dict(response.json())


def plan_for(client: TestClient, day: date, slots: list[dict[str, Any]]) -> dict[str, Any]:
    response = client.put(
        f"/api/day-plans/{day.isoformat()}",
        json={"id": f"plan-{day}", "date": day.isoformat(), "slots": slots},
    )
    assert response.status_code == HTTPStatus.OK
    return dict(response.json())


# ---------------------------------------------------------------- add / activate


@pytest.mark.api
def test_add_appends_free_sectors_and_is_idempotent(http_client):
    client, _clock = http_client
    make_task(client, "t-add")

    first = client.post(f"/api/day-plans/{TODAY}/add", json={"task_id": "t-add"})

    assert first.status_code == HTTPStatus.OK
    body = first.json()
    assert body["added"] == ["t-add"] and body["skipped"] == []
    assert [(s["sector"], s["task_id"]) for s in body["plan"]["slots"]] == [(1, "t-add")]

    again = client.post(f"/api/day-plans/{TODAY}/add", json={"task_id": "t-add"})
    same = again.json()
    assert same["added"] == [] and same["skipped"] == []
    assert same["plan"]["slots"] == body["plan"]["slots"]


@pytest.mark.api
def test_add_refuses_past_dates_and_unknown_tasks(http_client):
    client, _clock = http_client
    make_task(client, "t-yest")
    yesterday = (TODAY - timedelta(days=1)).isoformat()

    past = client.post(f"/api/day-plans/{yesterday}/add", json={"task_id": "t-yest"})
    missing = client.post(f"/api/day-plans/{TODAY}/add", json={"task_id": "ghost"})

    assert past.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert_detail_code(past, "invalid")
    assert "past" in past.json()["detail"]["message"]
    assert missing.status_code == HTTPStatus.NOT_FOUND
    assert_detail_code(missing, "not_found")


@pytest.mark.api
def test_activate_materializes_daily_once_keeps_manual_plan(http_client):
    client, _clock = http_client
    make_task(client, "t-daily", recurrence={"kind": "daily"})
    make_task(client, "t-once")
    make_task(client, "t-done", recurrence={"kind": "daily"})
    for to in ("planned", "doing", "done"):  # the full V7 chain
        client.post("/api/tasks/t-done/status", json={"to": to})
    plan_for(client, TODAY, [{"sector": 1, "task_id": "t-once"}])

    result = client.post(f"/api/day-plans/{TODAY}/activate")

    body = result.json()
    assert result.status_code == HTTPStatus.OK
    assert body["added"] == ["t-daily"]  # the done task is not materialized
    assert [(s["sector"], s["task_id"]) for s in body["plan"]["slots"]] == [
        (1, "t-once"),
        (2, "t-daily"),
    ]

    second = client.post(f"/api/day-plans/{TODAY}/activate")
    assert second.json()["added"] == []  # GWT-A2 over HTTP
    assert second.json()["plan"]["slots"] == body["plan"]["slots"]


@pytest.mark.api
def test_activate_full_day_reports_skip_not_error(http_client):
    client, _clock = http_client
    for n in range(12):
        make_task(client, f"t-f{n}")
    plan_for(
        client,
        TODAY,
        [{"sector": s, "task_id": f"t-f{s - 1}"} for s in range(1, 13)],
    )
    make_task(client, "t-late", recurrence={"kind": "daily"})

    result = client.post(f"/api/day-plans/{TODAY}/activate")

    assert result.status_code == HTTPStatus.OK  # honest outcome in the body
    assert result.json()["skipped"] == ["t-late"]


# ---------------------------------------------------------------- hints


@pytest.mark.api
def test_hints_are_empty_without_data_or_session(http_client):
    client, _clock = http_client

    response = client.get("/api/hints")

    assert response.status_code == HTTPStatus.OK
    assert response.json() == []


@pytest.mark.api
def test_diffuse_hint_fires_during_break_on_the_wire(http_client):
    client, clock = http_client
    make_task(client, "t-w", estimate_blocks=2)
    plan_for(client, TODAY, [{"sector": 1, "task_id": "t-w"}, {"sector": 2, "task_id": "t-w"}])
    started = client.post(
        "/api/sessions", json={"day_plan_id": f"plan-{TODAY}", "settings": FAST}
    ).json()
    assert started["phase"] == "work"

    clock.advance(timedelta(minutes=5))  # still inside the 10-min work block
    during_work = client.get("/api/hints").json()
    assert all(h["kind"] != "diffuse" for h in during_work)

    clock.advance(timedelta(minutes=6))  # work deadline crossed: now break
    view = client.get(f"/api/sessions/{started['id']}").json()  # catch-up runs
    assert view["phase"] == "break"
    on_break = client.get("/api/hints").json()
    assert on_break[0]["kind"] == "diffuse"  # spec 05: always first in a break


@pytest.mark.api
def test_einstellung_fires_after_two_interrupted_tomatoes(http_client):
    client, clock = http_client
    make_task(client, "t-x")
    plan_for(client, TODAY, [{"sector": 1, "task_id": "t-x"}])
    for _rounds in range(2):
        session = client.post(
            "/api/sessions", json={"day_plan_id": f"plan-{TODAY}", "settings": FAST}
        ).json()
        clock.advance(timedelta(minutes=12))
        client.post(f"/api/sessions/{session['id']}/stop")  # open WORK -> INTERRUPTED

    hints = client.get("/api/hints").json()

    einstellung = [h for h in hints if h["kind"] == "einstellung"]
    assert einstellung == [{"kind": "einstellung", "params": {"task_id": "t-x"}}]


@pytest.mark.api
def test_overlearning_fires_on_wall_burn_beyond_estimate(http_client):
    # paused wall minutes count as spent (WorkBlock law): 3 min + a 20-min
    # pause + finish = 30 min burned on a 1-block (10-min) task -> fires
    client, clock = http_client
    make_task(client, "t-o")
    plan_for(client, TODAY, [{"sector": 1, "task_id": "t-o"}])
    session = client.post(
        "/api/sessions", json={"day_plan_id": f"plan-{TODAY}", "settings": FAST}
    ).json()
    clock.advance(timedelta(minutes=3))
    client.post(f"/api/sessions/{session['id']}/pause")
    clock.advance(timedelta(minutes=20))
    client.post(f"/api/sessions/{session['id']}/resume")
    clock.advance(timedelta(minutes=10))

    hints = client.get("/api/hints").json()

    over = [h for h in hints if h["kind"] == "overlearning"]
    assert over == [{"kind": "overlearning", "params": {"task_id": "t-o"}}]


# ---------------------------------------------------------------- due queue


@pytest.mark.api
def test_due_queue_empty_until_a_study_review_lands(http_client):
    client, clock = http_client
    assert client.get("/api/repetitions/due").json() == []

    make_task(client, "t-study", type="study")
    plan_for(client, TODAY, [{"sector": 1, "task_id": "t-study"}])
    session = client.post(
        "/api/sessions", json={"day_plan_id": f"plan-{TODAY}", "settings": FAST}
    ).json()
    first_segment = session["timeline"][0]["id"]
    clock.advance(timedelta(minutes=11))
    client.get(f"/api/sessions/{session['id']}")  # catch-up closes the block
    reviewed = client.post("/api/reviews", json={"segment_id": first_segment, "score": 4})
    assert reviewed.status_code == HTTPStatus.CREATED  # ladder starts: due = today

    # science honesty (spec 01 §6.1): the first recall was TODAY, so the
    # next one is due today+3 — the queue is empty right until then.
    assert client.get("/api/repetitions/due").json() == []
    assert (
        client.get(f"/api/repetitions/due?as_of={(TODAY + timedelta(days=2)).isoformat()}").json()
        == []
    )

    on_day3 = client.get(
        f"/api/repetitions/due?as_of={(TODAY + timedelta(days=3)).isoformat()}"
    ).json()
    assert len(on_day3) == 1
    assert on_day3[0]["task_id"] == "t-study"
    assert on_day3[0]["title"] == "Task t-study"
    assert on_day3[0]["interval_idx"] == 1
    assert on_day3[0]["next_due"] == (TODAY + timedelta(days=3)).isoformat()
    assert on_day3[0]["overdue_days"] == 0

    overdue = client.get(
        f"/api/repetitions/due?as_of={(TODAY + timedelta(days=5)).isoformat()}"
    ).json()
    assert overdue[0]["overdue_days"] == 2  # honest "просрочено на N" data
