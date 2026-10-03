"""HTTP floor for the sprint lifecycle (E4c PR 2, spec 07 §4.2/§5.4/§5.5).

Covers: A25 (several active sprints, one still current), 5.4 lazy auto-close
with the frozen clock moved past the period, V34 gate + the fate menu
(carry-choice to sprint / shelf / leave, immutability), carry-choice-all,
and V29 cascade delete (children nullified, slots purged, segments detach).
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


@pytest.fixture
def live_app(tmp_path: Path) -> Iterator[tuple[TestClient, FakeClock]]:
    """Client + owning clock: auto-close and V20 need to move today."""
    app = create_app(tmp_path / "lifecycle-test.db")
    clock = FakeClock(DEFAULT_MOMENT)
    app.state.clock = clock
    with TestClient(app) as client:
        yield client, clock


def post_sprint(client: TestClient, start: str, end: str, **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"start_date": start, "end_date": end}
    body.update(extra)
    response = client.post("/api/sprints", json=body)
    assert response.status_code == HTTPStatus.CREATED, response.text
    return dict(response.json())


def activate(client: TestClient, sprint_id: str) -> dict[str, Any]:
    up = client.patch(f"/api/sprints/{sprint_id}", json={"status": "active"})
    assert up.status_code == HTTPStatus.OK, up.text
    return dict(up.json())


def make_task(client: TestClient, task_id: str, **body: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"id": task_id, "title": f"Card {task_id}", **body}
    response = client.post("/api/tasks", json=payload)
    assert response.status_code == HTTPStatus.CREATED, response.text
    return dict(response.json())


@pytest.mark.api
def test_active_sprint_auto_completes_on_first_read_after_its_dates(
    live_app: tuple[TestClient, FakeClock],
) -> None:
    """5.4: the write happens inside the read; the second call changes nothing."""
    client, clock = live_app
    sprint = activate(client, post_sprint(client, "2026-09-03", "2026-09-07")["id"])
    clock.advance(timedelta(days=5))  # today = 2026-09-08, period over

    listed = client.get("/api/sprints").json()

    assert [item["status"] for item in listed if item["id"] == sprint["id"]] == ["completed"]
    again = client.get("/api/sprints").json()  # idempotent catch-up
    assert [item["status"] for item in again if item["id"] == sprint["id"]] == ["completed"]


@pytest.mark.api
def test_two_active_sprints_catch_up_in_one_pass_without_fates(
    live_app: tuple[TestClient, FakeClock],
) -> None:
    """5.4 never waits for fate decisions: unfinished cards just light the "!"."""
    client, clock = live_app
    first = activate(client, post_sprint(client, "2026-09-03", "2026-09-05")["id"])
    second = activate(client, post_sprint(client, "2026-09-06", "2026-09-07")["id"])
    card = make_task(client, "t-open", sprint_id=first["id"])

    clock.advance(timedelta(days=5))  # today 2026-09-08: both periods fully past
    items = {item["id"]: item for item in client.get("/api/sprints").json()}

    assert items[first["id"]]["status"] == "completed"
    assert items[second["id"]]["status"] == "completed"
    assert items[first["id"]]["carry_pending"] == 1  # the "!" badge
    assert items[first["id"]]["unfinished_count"] == 1
    assert (
        client.get(f"/api/tasks/{card['id']}").json()["status"] == "backlog"
    )  # V33: tasks untouched


@pytest.mark.api
def test_activating_a_fully_expired_sprint_is_refused_when_v20_breaks(
    live_app: tuple[TestClient, FakeClock],
) -> None:
    client, clock = live_app
    planned = post_sprint(client, "2026-09-03", "2026-09-07")
    clock.advance(timedelta(days=5))

    refused = client.patch(f"/api/sprints/{planned['id']}", json={"status": "active"})

    assert refused.status_code == HTTPStatus.CONFLICT
    assert "no upcoming dates" in refused.json()["detail"]["message"]


@pytest.mark.api
def test_manual_completion_waits_for_every_fate_when_v34_breaks(
    live_app: tuple[TestClient, FakeClock],
) -> None:
    client, _ = live_app
    sprint = activate(client, post_sprint(client, "2026-09-03", "2026-09-07")["id"])
    make_task(client, "t-a", sprint_id=sprint["id"])
    make_task(client, "t-b", sprint_id=sprint["id"])

    blocked = client.patch(f"/api/sprints/{sprint['id']}", json={"status": "completed"})
    assert blocked.status_code == HTTPStatus.CONFLICT
    assert "2 unfinished" in blocked.json()["detail"]["message"]

    client.post(f"/api/tasks/{sprint['id']}/carry-choice", json={})  # 422 noise, ignored below
    client.post("/api/tasks/t-a/carry-choice", json={"leave": True})
    half = client.patch(f"/api/sprints/{sprint['id']}", json={"status": "completed"})
    assert half.status_code == HTTPStatus.CONFLICT  # one fate is not enough

    client.post("/api/tasks/t-b/carry-choice", json={"leave": True})
    done = client.patch(f"/api/sprints/{sprint['id']}", json={"status": "completed"})
    assert done.status_code == HTTPStatus.OK
    assert done.json()["carry_pending"] == 0  # the "!" went out


@pytest.mark.api
def test_carry_choice_moves_by_copy_and_freezes_the_fate(
    live_app: tuple[TestClient, FakeClock],
) -> None:
    """A27/A19/A40: copy in the new sprint, original MOVED and immutable."""
    client, clock = live_app
    closed = activate(client, post_sprint(client, "2026-09-03", "2026-09-07")["id"])
    shelf_next = activate(client, post_sprint(client, "2026-09-08", "2026-09-14")["id"])
    card = make_task(
        client,
        "t-move",
        sprint_id=closed["id"],
        recurrence={"kind": "on_dates", "days": ["2026-09-04", "2026-09-06"]},
        deadline="2026-09-30",
    )

    moved = client.post(
        f"/api/tasks/{card['id']}/carry-choice", json={"target_sprint_id": shelf_next["id"]}
    )

    assert moved.status_code == HTTPStatus.OK
    body = moved.json()
    assert body["carry_choice"] == "moved"
    assert body["recurrence"]["kind"] == "on_dates"  # the original keeps its ticks
    copies = client.get("/api/tasks", params={"sprint_id": shelf_next["id"]}).json()
    assert len(copies) == 1
    copy = copies[0]
    assert copy["id"] != card["id"]  # A27: a copy is a new card
    assert copy["cloned_from"] == card["id"]
    assert copy["status"] == "backlog"
    assert copy["recurrence"]["kind"] == "once"  # A19/4.2: ticks reset on the copy
    assert copy["deadline"] == "2026-09-30"  # deadline travels while still real

    clock.advance(timedelta(days=5))  # 2026-09-30 deadline is now in the past
    rewrite = client.post(f"/api/tasks/{card['id']}/carry-choice", json={"leave": True})
    assert rewrite.status_code == HTTPStatus.CONFLICT  # V34: decided is forever


@pytest.mark.api
def test_carry_choice_to_shelf_copies_without_a_expired_deadline(
    live_app: tuple[TestClient, FakeClock],
) -> None:
    """A19: a deadline that stopped meaning something does not travel."""
    client, clock = live_app
    sprint = activate(client, post_sprint(client, "2026-09-03", "2026-09-07")["id"])
    card = make_task(client, "t-shelf", sprint_id=sprint["id"], deadline="2026-09-05")
    clock.advance(timedelta(days=3))  # today 09-06: the deadline is behind us

    shelf = client.post(f"/api/tasks/{card['id']}/carry-choice", json={"target_sprint_id": None})

    assert shelf.status_code == HTTPStatus.OK
    assert shelf.json()["carry_choice"] == "moved"
    copies = client.get("/api/tasks", params={"no_sprint": "true"}).json()
    assert len(copies) == 1
    assert copies[0]["cloned_from"] == card["id"]
    assert copies[0]["sprint_id"] is None
    assert copies[0]["deadline"] is None  # A19: expired deadline reset
    left = client.post(f"/api/tasks/{card['id']}/carry-choice", json={"leave": True})
    assert left.status_code == HTTPStatus.CONFLICT  # decided is forever


@pytest.mark.api
def test_carry_choice_requires_an_explicit_answer(live_app: tuple[TestClient, FakeClock]) -> None:
    client, _ = live_app
    sprint = activate(client, post_sprint(client, "2026-09-03", "2026-09-07")["id"])
    card = make_task(client, "t-noop", sprint_id=sprint["id"])

    empty = client.post(f"/api/tasks/{card['id']}/carry-choice", json={})

    assert empty.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert_detail_code(empty, "invalid")


@pytest.mark.api
def test_carry_choice_all_freezes_every_open_fate_and_is_idempotent(
    live_app: tuple[TestClient, FakeClock],
) -> None:
    client, _ = live_app
    sprint = activate(client, post_sprint(client, "2026-09-03", "2026-09-07")["id"])
    make_task(client, "t-1", sprint_id=sprint["id"])
    make_task(client, "t-2", sprint_id=sprint["id"])
    done_card = make_task(client, "t-done", sprint_id=sprint["id"])
    client.post(f"/api/tasks/{done_card['id']}/status", json={"to": "planned"})
    client.post(f"/api/tasks/{done_card['id']}/status", json={"to": "doing"})
    client.post(f"/api/tasks/{done_card['id']}/status", json={"to": "done"})

    first = client.post(f"/api/sprints/{sprint['id']}/carry-choice-all")

    assert first.status_code == HTTPStatus.OK
    assert first.json() == {"decided": 2}  # done cards never need a fate
    again = client.post(f"/api/sprints/{sprint['id']}/carry-choice-all")
    assert again.json() == {"decided": 0}  # property: double click changes nothing
    fresh = client.get(f"/api/sprints/{sprint['id']}").json()
    assert fresh["carry_pending"] == 0
    assert fresh["tasks"]  # the sprint card lists its cards (spec 07 §6)


@pytest.mark.api
def test_delete_sprint_erases_cards_and_sweeps_footprints(
    live_app: tuple[TestClient, FakeClock],
) -> None:
    """V29 §5.5: children nullified, slots purged, segments detach, rows gone."""
    client, _ = live_app
    sprint = activate(client, post_sprint(client, "2026-09-03", "2026-09-07")["id"])
    parent = make_task(client, "t-parent", sprint_id=sprint["id"])
    child_outside = make_task(client, "t-child", parent_id=parent["id"])
    planned = make_task(client, "t-planned", sprint_id=sprint["id"])
    client.post(f"/api/tasks/{planned['id']}/status", json={"to": "planned"})
    client.post(
        "/api/day-plans/2026-09-04/add",
        json={"task_id": planned["id"]},
    )

    gone = client.delete(f"/api/sprints/{sprint['id']}")

    assert gone.status_code == HTTPStatus.NO_CONTENT
    assert client.get("/api/sprints").json() == []
    assert client.get(f"/api/tasks/{parent['id']}").status_code == HTTPStatus.NOT_FOUND
    assert client.get(f"/api/tasks/{planned['id']}").status_code == HTTPStatus.NOT_FOUND
    survivor = client.get(f"/api/tasks/{child_outside['id']}").json()
    assert survivor["parent_id"] is None  # children outlive the parent, FK never bites
    # The day plan is emptied and loses its row (drop_or_empty precedent).
    assert client.get("/api/day-plans/2026-09-04").status_code == HTTPStatus.NOT_FOUND


@pytest.mark.api
def test_completed_sprint_is_read_only_and_period_freezes_when_active(
    live_app: tuple[TestClient, FakeClock],
) -> None:
    client, _ = live_app
    sprint = activate(client, post_sprint(client, "2026-09-03", "2026-09-07")["id"])

    period = client.patch(f"/api/sprints/{sprint['id']}", json={"end_date": "2026-09-09"})
    texts = client.patch(f"/api/sprints/{sprint['id']}", json={"goal": "still editable"})

    assert period.status_code == HTTPStatus.CONFLICT
    assert texts.status_code == HTTPStatus.OK
    closed_ok = client.patch(f"/api/sprints/{sprint['id']}", json={"status": "completed"})
    assert closed_ok.status_code == HTTPStatus.OK  # no cards: closes silently
    edit_after = client.patch(f"/api/sprints/{sprint['id']}", json={"name": "renamed"})
    assert edit_after.status_code == HTTPStatus.CONFLICT
