"""HTTP floor for the done-trim wave (E4c PR 6, spec 07 §4.6, V26/A22).

«Готово» never outgrows `ui.done_visible_limit` per scope: arrivals write
their done_at and the oldest surplus leaves for ARCHIVED — immediately at
limit 0, and never across scope borders. The door is single (set_status,
close, review-walk, fold all route through complete()).
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

TODAY = DEFAULT_MOMENT.date()


@pytest.fixture
def trim_app(tmp_path: Path) -> Iterator[tuple[TestClient, FakeClock]]:
    app = create_app(tmp_path / "done-trim-test.db")
    clock = FakeClock(DEFAULT_MOMENT)
    app.state.clock = clock
    with TestClient(app) as client:
        yield client, clock


def make_task(client: TestClient, task_id: str, **body: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"id": task_id, "title": f"Card {task_id}", **body}
    response = client.post("/api/tasks", json=payload)
    assert response.status_code == HTTPStatus.CREATED, response.text
    return dict(response.json())


def close_task(client: TestClient, task_id: str) -> dict[str, Any]:
    put_in_work(client, task_id)
    response = client.post(f"/api/tasks/{task_id}/status", json={"to": "done"})
    assert response.status_code == HTTPStatus.OK, response.text
    return dict(response.json())


def set_limit(client: TestClient, limit: int) -> None:
    response = client.put(
        "/api/settings/ui",
        json={"max_in_work": 6, "theme": "auto", "done_visible_limit": limit},
    )
    assert response.status_code == HTTPStatus.OK, response.text


def ids(client: TestClient, **params: Any) -> list[str]:
    """Task ids of one status/scope slice (the helper's params are filters)."""
    response = client.get("/api/tasks", params=params)
    assert response.status_code == HTTPStatus.OK
    return [str(item["id"]) for item in response.json()]


@pytest.mark.api
def test_moving_into_done_stamps_the_completion_clock(
    trim_app: tuple[TestClient, FakeClock],
) -> None:
    """§4.6 (author 03.10): the record is written at the moment of closing."""
    client, clock = trim_app
    make_task(client, "t-stamp")

    body = close_task(client, "t-stamp")

    assert body["status"] == "done"
    listed = client.get("/api/tasks", params={"status": "done"}).json()
    assert listed[0]["done_at"] == clock.now().isoformat()


@pytest.mark.api
def test_done_column_keeps_the_newest_and_archives_the_oldest(
    trim_app: tuple[TestClient, FakeClock],
) -> None:
    """V26: over the limit, the earliest finished card leaves first."""
    client, clock = trim_app
    set_limit(client, 2)
    for task_id in ("t-1", "t-2", "t-3"):
        make_task(client, task_id)
    close_task(client, "t-1")
    clock.advance(timedelta(days=1))
    close_task(client, "t-2")
    clock.advance(timedelta(days=1))
    close_task(client, "t-3")

    done = ids(client, status="done")
    archived = ids(client, status="archived")
    assert sorted(done) == ["t-2", "t-3"]
    assert archived == ["t-1"]


@pytest.mark.api
def test_reopen_and_reclose_rewrites_the_stamp_and_the_order(
    trim_app: tuple[TestClient, FakeClock],
) -> None:
    """done_at is the LAST arrival: reopening and closing re-files the card."""
    client, clock = trim_app
    set_limit(client, 1)
    make_task(client, "old")
    make_task(client, "new")
    close_task(client, "old")
    clock.advance(timedelta(days=1))
    close_task(client, "new")  # trims "old" away
    assert ids(client, status="archived") == ["old"]

    # the archived card returns (V7) and gets a fresh finish — now IT is
    # newest, so the trim pushes the old "new" out instead. The stamp is
    # the LAST arrival, not the first ever.
    back = client.post("/api/tasks/old/status", json={"to": "backlog"})
    assert back.status_code == HTTPStatus.OK
    clock.advance(timedelta(days=1))
    close_task(client, "old")

    assert ids(client, status="done") == ["old"]
    assert ids(client, status="archived") == ["new"]


@pytest.mark.api
def test_limit_zero_archives_on_arrival(trim_app: tuple[TestClient, FakeClock]) -> None:
    """§4.6: at limit 0 «Готово» stays empty — the card leaves in the same write."""
    client, _clock = trim_app
    set_limit(client, 0)
    make_task(client, "t-now")

    closed = close_task(client, "t-now")

    assert closed["status"] == "archived"
    assert ids(client, status="done") == []
    assert ids(client, status="archived") == ["t-now"]


@pytest.mark.api
def test_trim_never_crosses_the_scope_border(
    trim_app: tuple[TestClient, FakeClock],
) -> None:
    """§4.6: the limit lives per scope — a sprint overflow spares the shelf."""
    client, _clock = trim_app
    sprint = client.post(
        "/api/sprints",
        json={"start_date": str(TODAY), "end_date": str(TODAY + timedelta(days=3))},
    )
    sprint_id = str(sprint.json()["id"])
    client.patch(f"/api/sprints/{sprint_id}", json={"status": "active"})
    set_limit(client, 1)
    make_task(client, "shelf", sprint_id=None)
    make_task(client, "sp-1", sprint_id=sprint_id)
    make_task(client, "sp-2", sprint_id=sprint_id)

    close_task(client, "shelf")
    close_task(client, "sp-1")
    close_task(client, "sp-2")

    # the shelf card survived its own scope (it was alone there)
    assert ids(client, status="done", no_sprint="true") == ["shelf"]
    assert sorted(ids(client, status="done", sprint_id=sprint_id)) == ["sp-2"]
    assert ids(client, status="archived", sprint_id=sprint_id) == ["sp-1"]


@pytest.mark.api
def test_done_limit_is_validated_on_put(trim_app: tuple[TestClient, FakeClock]) -> None:
    """§6 additive: the settings wire takes 0..30, nothing beyond."""
    client, _clock = trim_app
    bad = client.put(
        "/api/settings/ui",
        json={"max_in_work": 6, "theme": "auto", "done_visible_limit": 31},
    )
    assert bad.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    ok = client.get("/api/settings").json()["ui"]
    assert ok["done_visible_limit"] == 10  # untouched by the refused write
