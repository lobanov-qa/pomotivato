"""HTTP floor for sprints: CRUD, numbering, V19 overlap/forward rules (spec 07).

E4c PR 1 rewires the old E4b floor: frozen clock is 2026-09-03, so every
created period starts today or later (V19 creation — DF18 retrospective
periods retired); completed sprints are no longer overlap-exempt (V19 full
scope, ADR-0005). The "one active" guard still lives here until PR 2 (A25).
"""

from __future__ import annotations

from collections.abc import Iterator
from http import HTTPStatus
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pomotivato.api.schemas import SprintDto
from pomotivato.core.clock import FakeClock
from pomotivato.main import create_app
from tests.api.schemas_http import assert_detail_code, validate_as
from tests.factories.core_models import DEFAULT_MOMENT


@pytest.fixture
def http_app(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(tmp_path / "sprints-test.db")
    app.state.clock = FakeClock(DEFAULT_MOMENT)
    with TestClient(app) as client:
        yield client


def post_sprint(client: TestClient, start: str, end: str, **extra: object) -> dict[str, object]:
    body: dict[str, object] = {"start_date": start, "end_date": end}
    body.update(extra)
    response = client.post("/api/sprints", json=body)
    assert response.status_code == HTTPStatus.CREATED, response.text
    return dict(response.json())


@pytest.mark.api
def test_create_assigns_server_numbers_and_lists_newest_first(http_app: TestClient) -> None:
    first = post_sprint(http_app, "2026-09-03", "2026-09-07", name="w36")
    second = post_sprint(http_app, "2026-09-08", "2026-09-14", name="w37")

    assert first["number"] == 1 and second["number"] == 2
    assert first["status"] == "planned"

    listing = http_app.get("/api/sprints")
    numbers = [item["number"] for item in listing.json()]
    assert numbers == [2, 1]
    validate_as(SprintDto, listing.json()[0])


@pytest.mark.api
def test_retrospective_period_is_rejected_when_v19_creation_breaks(
    http_app: TestClient,
) -> None:
    """E4c (ADR-0005): a sprint cannot start in the past any more — DF18 died."""
    bad = http_app.post("/api/sprints", json={"start_date": "2026-09-01", "end_date": "2026-09-05"})

    assert bad.status_code == HTTPStatus.CONFLICT
    assert_detail_code(bad, "conflict")
    assert "in the past" in bad.json()["detail"]["message"]
    assert http_app.get("/api/sprints").json() == []  # rejected create stuck nothing


@pytest.mark.api
def test_overlap_with_open_sprint_is_conflict(http_app: TestClient) -> None:
    post_sprint(http_app, "2026-09-03", "2026-09-07")

    bad = http_app.post("/api/sprints", json={"start_date": "2026-09-05", "end_date": "2026-09-10"})

    assert bad.status_code == HTTPStatus.CONFLICT
    assert_detail_code(bad, "conflict")
    assert "overlaps" in bad.json()["detail"]["message"]


@pytest.mark.api
def test_completed_sprint_is_no_longer_overlap_exempt(http_app: TestClient) -> None:
    """V19 full scope (spec 07 §5): non-overlap keeps "current sprint" unique."""
    done = post_sprint(http_app, "2026-09-03", "2026-09-07")
    http_app.patch(f"/api/sprints/{done['id']}", json={"status": "active"})
    http_app.patch(f"/api/sprints/{done['id']}", json={"status": "completed"})

    clash = http_app.post(
        "/api/sprints", json={"start_date": "2026-09-05", "end_date": "2026-09-08"}
    )

    assert clash.status_code == HTTPStatus.CONFLICT


@pytest.mark.api
def test_several_sprints_can_be_active_together_when_a25_lifts_the_guard(
    http_app: TestClient,
) -> None:
    """ADR-0005/A25 (E4c PR 2): the "≤1 active" invariant is gone; the
    non-overlapping periods keep the current sprint unique instead."""
    first = post_sprint(http_app, "2026-09-03", "2026-09-07")
    second = post_sprint(http_app, "2026-09-08", "2026-09-14")
    assert (
        http_app.patch(f"/api/sprints/{first['id']}", json={"status": "active"}).status_code
        == HTTPStatus.OK
    )

    activated = http_app.patch(f"/api/sprints/{second['id']}", json={"status": "active"})

    assert activated.status_code == HTTPStatus.OK
    fresh = {item["id"]: item for item in http_app.get("/api/sprints").json()}
    assert fresh[first["id"]]["status"] == "active"
    assert fresh[second["id"]]["status"] == "active"
    # Exactly one carries the date (the band never shows two "current").
    currents = [item for item in fresh.values() if item["is_current"]]
    assert [c["id"] for c in currents] == [first["id"]]


@pytest.mark.api
def test_active_period_freezes_and_completed_is_read_only(http_app: TestClient) -> None:
    """E4c PR 2 (4.1 status table): after activation the period stops moving;
    a completed container answers edits with 409, deletes stay allowed."""
    created = post_sprint(http_app, "2026-09-03", "2026-09-07", goal="ship E4b")
    edited = http_app.patch(
        f"/api/sprints/{created['id']}",
        json={"name": "sprint 36", "goal": "ship E4b+UX", "end_date": "2026-09-09"},
    )
    body = edited.json()
    assert body["name"] == "sprint 36"
    assert body["goal"] == "ship E4b+UX"
    assert body["end_date"] == "2026-09-09"
    too_long = http_app.patch(f"/api/sprints/{created['id']}", json={"end_date": "2026-09-30"})
    assert too_long.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    http_app.patch(f"/api/sprints/{created['id']}", json={"status": "active"})
    frozen = http_app.patch(f"/api/sprints/{created['id']}", json={"end_date": "2026-09-04"})
    assert frozen.status_code == HTTPStatus.CONFLICT
    texts_ok = http_app.patch(f"/api/sprints/{created['id']}", json={"goal": "still editable"})
    assert texts_ok.status_code == HTTPStatus.OK

    closed = http_app.patch(f"/api/sprints/{created['id']}", json={"status": "completed"})
    assert closed.status_code == HTTPStatus.OK  # no cards: no fate gate
    read_only = http_app.patch(f"/api/sprints/{created['id']}", json={"goal": "no more"})
    assert read_only.status_code == HTTPStatus.CONFLICT


@pytest.mark.api
def test_unknown_sprint_is_404_and_bad_status_is_422(http_app: TestClient) -> None:
    missing = http_app.patch("/api/sprints/sprint-nope", json={"status": "active"})
    assert missing.status_code == HTTPStatus.NOT_FOUND
    assert_detail_code(missing, "not_found")

    created = post_sprint(http_app, "2026-09-03", "2026-09-07")
    bad = http_app.patch(f"/api/sprints/{created['id']}", json={"status": "canceled"})
    assert bad.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert_detail_code(bad, "invalid")


@pytest.mark.api
def test_completed_cannot_reopen(http_app: TestClient) -> None:
    created = post_sprint(http_app, "2026-09-03", "2026-09-07")
    http_app.patch(f"/api/sprints/{created['id']}", json={"status": "active"})
    http_app.patch(f"/api/sprints/{created['id']}", json={"status": "completed"})

    reopen = http_app.patch(f"/api/sprints/{created['id']}", json={"status": "planned"})

    assert reopen.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
