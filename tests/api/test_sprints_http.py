"""HTTP floor for sprints: CRUD, numbering, overlap/active conflicts (spec 05 §3.10)."""

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
    first = post_sprint(http_app, "2026-09-01", "2026-09-07", name="w36")
    second = post_sprint(http_app, "2026-09-08", "2026-09-14", name="w37")

    assert first["number"] == 1 and second["number"] == 2
    assert first["status"] == "planned"

    listing = http_app.get("/api/sprints")
    numbers = [item["number"] for item in listing.json()]
    assert numbers == [2, 1]
    validate_as(SprintDto, listing.json()[0])


@pytest.mark.api
def test_overlap_with_open_sprint_is_conflict(http_app: TestClient) -> None:
    post_sprint(http_app, "2026-09-01", "2026-09-07")

    bad = http_app.post("/api/sprints", json={"start_date": "2026-09-05", "end_date": "2026-09-10"})

    assert bad.status_code == HTTPStatus.CONFLICT
    assert_detail_code(bad, "conflict")
    assert "overlaps" in bad.json()["detail"]["message"]


@pytest.mark.api
def test_completed_sprint_may_be_overlapped_by_history(http_app: TestClient) -> None:
    done = post_sprint(http_app, "2026-09-01", "2026-09-07")
    http_app.patch(f"/api/sprints/{done['id']}", json={"status": "active"})
    http_app.patch(f"/api/sprints/{done['id']}", json={"status": "completed"})

    again = http_app.post(
        "/api/sprints", json={"start_date": "2026-09-03", "end_date": "2026-09-08"}
    )

    assert again.status_code == HTTPStatus.CREATED  # ⚑ Q9: history is not blocked


@pytest.mark.api
def test_only_one_active_sprint_at_a_time(http_app: TestClient) -> None:
    first = post_sprint(http_app, "2026-09-01", "2026-09-07")
    second = post_sprint(http_app, "2026-09-08", "2026-09-14")
    assert (
        http_app.patch(f"/api/sprints/{first['id']}", json={"status": "active"}).status_code
        == HTTPStatus.OK
    )

    clash = http_app.patch(f"/api/sprints/{second['id']}", json={"status": "active"})

    assert clash.status_code == HTTPStatus.CONFLICT
    assert "already active" in clash.json()["detail"]["message"]
    fresh = http_app.get("/api/sprints").json()
    statuses = {item["id"]: item["status"] for item in fresh}
    assert statuses[second["id"]] == "planned"  # rejected patch stuck nothing


@pytest.mark.api
def test_patch_edits_texts_and_period_and_revalidates(http_app: TestClient) -> None:
    created = post_sprint(http_app, "2026-09-01", "2026-09-07", goal="ship E4b")

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


@pytest.mark.api
def test_unknown_sprint_is_404_and_bad_status_is_422(http_app: TestClient) -> None:
    missing = http_app.patch("/api/sprints/sprint-nope", json={"status": "active"})
    assert missing.status_code == HTTPStatus.NOT_FOUND
    assert_detail_code(missing, "not_found")

    created = post_sprint(http_app, "2026-09-01", "2026-09-07")
    bad = http_app.patch(f"/api/sprints/{created['id']}", json={"status": "canceled"})
    assert bad.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert_detail_code(bad, "invalid")


@pytest.mark.api
def test_completed_cannot_reopen(http_app: TestClient) -> None:
    created = post_sprint(http_app, "2026-09-01", "2026-09-07")
    http_app.patch(f"/api/sprints/{created['id']}", json={"status": "active"})
    http_app.patch(f"/api/sprints/{created['id']}", json={"status": "completed"})

    reopen = http_app.patch(f"/api/sprints/{created['id']}", json={"status": "planned"})

    assert reopen.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
