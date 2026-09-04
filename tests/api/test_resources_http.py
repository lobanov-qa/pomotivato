"""HTTP floor for resources: tasks / day-plans / settings (spec 02 §5, §8).

TestClient against a real temp-SQLite; app.state.clock is a FakeClock so
created_at is deterministic without monkeypatching (injectable clock).
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
from tests.api.schemas_http import TaskDto, assert_detail_code
from tests.factories.core_models import DEFAULT_MOMENT


@pytest.fixture
def http_app(tmp_path: Path) -> Iterator[TestClient]:
    """Client over a migrated temp database with a frozen clock."""
    app = create_app(tmp_path / "resources-test.db")
    app.state.clock = FakeClock(DEFAULT_MOMENT)
    with TestClient(app) as client:
        yield client


def _task_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"id": "task-100", "title": "Write E2 tests"}
    payload.update(overrides)
    return payload


@pytest.mark.api
def test_create_task_returns_dto_when_valid_payload(http_app):
    response = http_app.post("/api/tasks", json=_task_payload())

    assert response.status_code == HTTPStatus.CREATED
    dto = TaskDto.model_validate(response.json())
    assert dto.id == "task-100"
    assert dto.status == "backlog"
    assert dto.created_at == DEFAULT_MOMENT.isoformat()


@pytest.mark.api
def test_create_task_conflicts_when_duplicate_id(http_app):
    http_app.post("/api/tasks", json=_task_payload())

    second = http_app.post("/api/tasks", json=_task_payload(estimate_blocks=2))

    assert second.status_code == HTTPStatus.CONFLICT


@pytest.mark.api
def test_get_task_404_when_unknown(http_app):
    response = http_app.get("/api/tasks/ghost")

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert_detail_code(response, "not_found")


@pytest.mark.api
def test_list_tasks_filters_when_status_given(http_app):
    http_app.post("/api/tasks", json=_task_payload())
    http_app.post("/api/tasks", json=_task_payload(id="task-101", title="Second"))
    http_app.post("/api/tasks/task-101/status", json={"to": "archived"})

    backlog = http_app.get("/api/tasks", params={"status": "backlog"})
    archived = http_app.get("/api/tasks", params={"status": "archived"})

    assert [t["id"] for t in backlog.json()] == ["task-100"]
    assert [t["id"] for t in archived.json()] == ["task-101"]


@pytest.mark.api
def test_patch_task_clears_optional_when_null_sent(http_app):
    http_app.post("/api/tasks", json=_task_payload(when_then="then I focus"))

    patched = http_app.patch("/api/tasks/task-100", json={"when_then": None, "urgent": True})

    assert patched.status_code == HTTPStatus.OK
    body = patched.json()
    assert body["when_then"] is None
    assert body["urgent"] is True


@pytest.mark.api
def test_patch_rejects_blank_title_when_v1_breaks(http_app):
    http_app.post("/api/tasks", json=_task_payload())

    response = http_app.patch("/api/tasks/task-100", json={"title": "  "})

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert_detail_code(response, "invalid")


@pytest.mark.api
def test_status_machine_maps_illegal_move_to_409(http_app):
    http_app.post("/api/tasks", json=_task_payload())

    response = http_app.post("/api/tasks/task-100/status", json={"to": "done"})

    assert response.status_code == HTTPStatus.CONFLICT
    assert_detail_code(response, "conflict")


@pytest.mark.api
def test_delete_backlog_task_returns_204_then_404(http_app):
    http_app.post("/api/tasks", json=_task_payload())

    deleted = http_app.delete("/api/tasks/task-100")
    fetched = http_app.get("/api/tasks/task-100")

    assert deleted.status_code == HTTPStatus.NO_CONTENT
    assert fetched.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.api
def test_delete_conflicts_when_task_is_doing(http_app):
    http_app.post("/api/tasks", json=_task_payload())
    http_app.post("/api/tasks/task-100/status", json={"to": "planned"})
    http_app.post("/api/tasks/task-100/status", json={"to": "doing"})

    response = http_app.delete("/api/tasks/task-100")

    assert response.status_code == HTTPStatus.CONFLICT


@pytest.mark.api
def test_day_plan_upsert_get_and_move_over_http(http_app):
    http_app.post("/api/tasks", json=_task_payload())
    http_app.post("/api/tasks", json=_task_payload(id="task-101", title="Another"))
    plan = {
        "id": "plan-x",
        "date": DEFAULT_MOMENT.date().isoformat(),
        "slots": [
            {"sector": 1, "task_id": "task-100"},
            {"sector": 2, "task_id": "task-101"},
        ],
    }

    created = http_app.put("/api/day-plans/2026-09-03", json=plan)
    moved = http_app.post("/api/day-plans/2026-09-03/slots/move", json={"from": 2, "to": 1})
    fetched = http_app.get("/api/day-plans/2026-09-03")

    assert created.status_code == HTTPStatus.OK
    assert moved.status_code == HTTPStatus.OK
    assert [s["task_id"] for s in moved.json()["slots"]] == ["task-101", "task-100"]
    assert fetched.json()["slots"] == moved.json()["slots"]


@pytest.mark.api
def test_day_plan_422_when_slot_unknown_task(http_app):
    plan = {
        "id": "plan-ghost",
        "date": DEFAULT_MOMENT.date().isoformat(),
        "slots": [{"sector": 1, "task_id": "ghost-task"}],
    }

    response = http_app.put("/api/day-plans/2026-09-03", json=plan)

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.api
def test_settings_roundtrip_and_v5_rejection(http_app):
    default = http_app.get("/api/settings")
    assert default.json() == {
        "work_min": 25,
        "break_min": 5,
        "long_break_min": 15,
        "long_break_every": 4,
        "auto_start_next": True,
    }

    ok = http_app.put(
        "/api/settings",
        json={
            "work_min": 50,
            "break_min": 10,
            "long_break_min": 15,
            "long_break_every": 3,
            "auto_start_next": False,
        },
    )
    bad = http_app.put(
        "/api/settings",
        json={
            "work_min": 500,
            "break_min": 5,
            "long_break_min": 15,
            "long_break_every": 4,
            "auto_start_next": True,
        },
    )
    after_bad = http_app.get("/api/settings")

    assert ok.status_code == HTTPStatus.OK
    assert bad.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert after_bad.json()["work_min"] == 50  # rollback: bad PUT did not stick
