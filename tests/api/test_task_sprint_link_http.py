"""HTTP floor for the task<->sprint link (E4c PR 1, spec 07 §6).

Covers the board-scope filters (sprint_id / no_sprint), container guards on
write (V18 unknown sprint 404, V28 planned target 409, V19 ticks-outside 409)
and the single move of a card between active sprints / onto the dateless
shelf (A36). Sprint dates respect V19-creation: frozen clock is 2026-09-03.
"""

from __future__ import annotations

from collections.abc import Iterator
from http import HTTPStatus
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from pomotivato.core.clock import FakeClock
from pomotivato.main import create_app
from tests.api.schemas_http import TaskDto, assert_detail_code, put_in_work, validate_as
from tests.factories.core_models import DEFAULT_MOMENT


@pytest.fixture
def http_app(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(tmp_path / "link-test.db")
    app.state.clock = FakeClock(DEFAULT_MOMENT)
    with TestClient(app) as client:
        yield client


def make_sprint(client: TestClient, start: str, end: str, *, activate: bool = True) -> str:
    response = client.post("/api/sprints", json={"start_date": start, "end_date": end})
    assert response.status_code == HTTPStatus.CREATED, response.text
    body: dict[str, object] = response.json()
    sprint_id = str(body["id"])
    if activate:
        up = client.patch(f"/api/sprints/{sprint_id}", json={"status": "active"})
        assert up.status_code == HTTPStatus.OK, up.text
    return sprint_id


def make_task(client: TestClient, **body: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"id": f"task-{len(client.get('/api/tasks').json()) + 1}", **body}
    payload.setdefault("title", f"Card {payload['id']}")
    response = client.post("/api/tasks", json=payload)
    assert response.status_code == HTTPStatus.CREATED, response.text
    return dict(response.json())


@pytest.mark.api
def test_task_created_without_sprint_lands_on_the_dateless_shelf(
    http_app: TestClient,
) -> None:
    created = make_task(http_app, title="Sandbox card")
    assert created["sprint_id"] is None
    validate_as(TaskDto, created)

    shelf = http_app.get("/api/tasks", params={"no_sprint": "true"})
    assert [t["id"] for t in shelf.json()] == [created["id"]]


@pytest.mark.api
def test_task_created_in_active_sprint_keeps_the_link(http_app: TestClient) -> None:
    sprint = make_sprint(http_app, "2026-09-03", "2026-09-07")

    created = make_task(http_app, sprint_id=sprint)

    assert created["sprint_id"] == sprint
    listed = http_app.get("/api/tasks", params={"sprint_id": sprint})
    assert [t["id"] for t in listed.json()] == [created["id"]]
    other = http_app.get("/api/tasks", params={"sprint_id": "sprint-ghost", "no_sprint": "false"})
    assert other.json() == []  # unknown filter value is data, not a refusal


@pytest.mark.api
def test_create_task_in_planned_sprint_refuses_when_v28_breaks(http_app: TestClient) -> None:
    planned = make_sprint(http_app, "2026-09-03", "2026-09-07", activate=False)

    bad = http_app.post("/api/tasks", json={"id": "t1", "title": "Too early", "sprint_id": planned})

    assert bad.status_code == HTTPStatus.CONFLICT
    assert_detail_code(bad, "conflict")
    assert "not activated" in bad.json()["detail"]["message"]


@pytest.mark.api
def test_create_task_with_unknown_sprint_is_404_when_v18_breaks(http_app: TestClient) -> None:
    bad = http_app.post(
        "/api/tasks", json={"id": "t1", "title": "Ghost box", "sprint_id": "sprint-ghost"}
    )

    assert bad.status_code == HTTPStatus.NOT_FOUND
    assert_detail_code(bad, "not_found")


@pytest.mark.api
def test_patch_rejects_marks_outside_period_and_move_into_planned_sprint(
    http_app: TestClient,
) -> None:
    """PATCH rides the same V19/V28 gates as create (A31/A36 checks on the
    UPDATED card); a second active sprint is impossible until the "one
    active" guard is lifted in PR 2 (A25), so the move target is planned."""
    sprint = make_sprint(http_app, "2026-09-03", "2026-09-07")
    card = make_task(http_app, sprint_id=sprint)

    outside = http_app.patch(
        f"/api/tasks/{card['id']}",
        json={"recurrence": {"kind": "on_dates", "days": ["2026-09-04", "2026-09-20"]}},
    )
    assert outside.status_code == HTTPStatus.CONFLICT
    assert "outside sprint period" in outside.json()["detail"]["message"]
    assert http_app.get(f"/api/tasks/{card['id']}").json()["recurrence"]["kind"] == "once"

    planned = make_sprint(http_app, "2026-09-08", "2026-09-14", activate=False)
    too_early = http_app.patch(f"/api/tasks/{card['id']}", json={"sprint_id": planned})
    assert too_early.status_code == HTTPStatus.CONFLICT
    assert "not activated" in too_early.json()["detail"]["message"]

    # Marks inside the period are accepted, and the link survives the edit.
    ok = http_app.patch(
        f"/api/tasks/{card['id']}",
        json={"recurrence": {"kind": "on_dates", "days": ["2026-09-04", "2026-09-06"]}},
    )
    assert ok.status_code == HTTPStatus.OK
    assert ok.json()["sprint_id"] == sprint


@pytest.mark.api
def test_explicit_null_sprint_takes_the_card_off_to_the_shelf(http_app: TestClient) -> None:
    sprint = make_sprint(http_app, "2026-09-03", "2026-09-07")
    card = make_task(http_app, sprint_id=sprint)

    moved = http_app.patch(f"/api/tasks/{card['id']}", json={"sprint_id": None})

    assert moved.json()["sprint_id"] is None
    shelf = http_app.get("/api/tasks", params={"no_sprint": "true"})
    assert [t["id"] for t in shelf.json()] == [card["id"]]


@pytest.mark.api
def test_patch_without_sprint_key_leaves_the_link_untouched(http_app: TestClient) -> None:
    sprint = make_sprint(http_app, "2026-09-03", "2026-09-07")
    card = make_task(http_app, sprint_id=sprint)

    edited = http_app.patch(f"/api/tasks/{card['id']}", json={"title": "Renamed"})

    assert edited.json()["sprint_id"] == sprint


@pytest.mark.api
def test_clone_into_completed_sprint_is_refused_when_v28_breaks(http_app: TestClient) -> None:
    sprint = make_sprint(http_app, "2026-09-03", "2026-09-07")
    make_task(http_app, id="t-done", sprint_id=sprint)
    put_in_work(http_app, "t-done")
    http_app.post("/api/tasks/t-done/status", json={"to": "done"})
    closed = http_app.patch(f"/api/sprints/{sprint}", json={"status": "completed"})
    assert closed.status_code == HTTPStatus.OK

    refused = http_app.post("/api/tasks/t-done/clone", json={"id": "t-copy"})

    assert refused.status_code == HTTPStatus.CONFLICT
    assert "not activated" in refused.json()["detail"]["message"]
