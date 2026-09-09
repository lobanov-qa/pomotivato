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
def test_doing_transition_respects_capacity_gate(http_app):
    """Funnel law server-side: the (N+1)-th card into doing gets 409."""
    for i in range(3):
        created = http_app.post("/api/tasks", json=_task_payload(id=f"cap-{i}", title=f"Cap {i}"))
        assert created.status_code == HTTPStatus.CREATED
        planned = http_app.post(f"/api/tasks/cap-{i}/status", json={"to": "planned"})
        assert planned.status_code == HTTPStatus.OK

    limited = http_app.put("/api/settings/ui", json={"max_in_work": 2, "theme": "auto"})
    assert limited.status_code == HTTPStatus.OK

    first = http_app.post("/api/tasks/cap-0/status", json={"to": "doing"})
    second = http_app.post("/api/tasks/cap-1/status", json={"to": "doing"})
    third = http_app.post("/api/tasks/cap-2/status", json={"to": "doing"})

    assert first.status_code == second.status_code == HTTPStatus.OK
    assert third.status_code == HTTPStatus.CONFLICT
    assert "2" in third.json()["detail"]["message"]
    # a task LEAVING doing frees capacity for the next one
    http_app.post("/api/tasks/cap-0/status", json={"to": "planned"})
    retry = http_app.post("/api/tasks/cap-2/status", json={"to": "doing"})
    assert retry.status_code == HTTPStatus.OK


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
def test_delete_backlog_task_purges_past_day_slot(http_app):
    """DF1 over HTTP: yesterday's ghost slot is swept away with the card."""
    http_app.post("/api/tasks", json=_task_payload())
    http_app.post("/api/tasks", json=_task_payload(id="task-101", title="Keeper"))
    http_app.put(
        "/api/day-plans/2026-09-01",
        json={
            "id": "plan-old",
            "date": "2026-09-01",
            "slots": [{"sector": 1, "task_id": "task-100"}],
        },
    )

    deleted = http_app.delete("/api/tasks/task-100")
    plan = http_app.get("/api/day-plans/2026-09-01")

    assert deleted.status_code == HTTPStatus.NO_CONTENT
    assert plan.status_code == HTTPStatus.NOT_FOUND


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
        "session": {
            "work_min": 25,
            "break_min": 5,
            "long_break_min": 15,
            "long_break_every": 4,
            "auto_start_next": True,
            "strict_mode": False,
            "warmup_min": 0,
            "special_breaks": [],
        },
        "ui": {
            "max_in_work": 6,
            "theme": "auto",
            "require_science_fields": False,
            "wet_hints": True,
        },
    }

    ok = http_app.put(
        "/api/settings/session",
        json={
            "work_min": 50,
            "break_min": 10,
            "long_break_min": 15,
            "long_break_every": 3,
            "auto_start_next": False,
        },
    )
    bad = http_app.put(
        "/api/settings/session",
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
    assert after_bad.json()["session"]["work_min"] == 50  # rollback: bad PUT stuck nothing


@pytest.mark.api
def test_ui_settings_roundtrip_keeps_session_key(http_app):
    before = http_app.get("/api/settings").json()["session"]

    ok = http_app.put("/api/settings/ui", json={"max_in_work": 9, "theme": "dark"})
    after = http_app.get("/api/settings").json()

    assert ok.status_code == HTTPStatus.OK
    assert after["ui"] == {
        "max_in_work": 9,
        "theme": "dark",
        "require_science_fields": False,
        "wet_hints": True,
    }
    assert after["session"] == before  # keys are independent (spec 03 §9)


@pytest.mark.api
def test_ui_settings_rejects_capacity_outside_1_12(http_app):
    for value in (0, 13):
        response = http_app.put("/api/settings/ui", json={"max_in_work": value, "theme": "auto"})
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, value

    after = http_app.get("/api/settings").json()
    assert after["ui"]["max_in_work"] == 6  # default untouched


@pytest.mark.api
def test_ui_wet_hints_toggles_off_and_back_when_timer_first(http_app):
    """DF6 (spec 06): the amber science-ring switch is a persisted ui flag."""
    off = http_app.put(
        "/api/settings/ui",
        json={
            "max_in_work": 6,
            "theme": "auto",
            "require_science_fields": False,
            "wet_hints": False,
        },
    )
    assert off.status_code == HTTPStatus.OK

    after = http_app.get("/api/settings").json()
    assert after["ui"]["wet_hints"] is False
    # the hard V8 gate is a different switch — off must not flip it on
    assert after["ui"]["require_science_fields"] is False

    on = http_app.put(
        "/api/settings/ui",
        json={
            "max_in_work": 6,
            "theme": "auto",
            "require_science_fields": False,
            "wet_hints": True,
        },
    )
    assert on.json()["wet_hints"] is True


@pytest.mark.api
def test_ui_settings_rejects_unknown_theme(http_app):
    response = http_app.put("/api/settings/ui", json={"max_in_work": 6, "theme": "hotdog"})

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.api
def test_clone_endpoint_returns_backlog_copy_with_lineage(http_app):
    """DF12 over HTTP: POST /api/tasks/{id}/clone -> 201 backlog twin."""
    http_app.post("/api/tasks", json=_task_payload())
    http_app.post("/api/tasks/task-100/status", json={"to": "planned"})
    http_app.post("/api/tasks/task-100/status", json={"to": "doing"})
    http_app.post("/api/tasks/task-100/status", json={"to": "done"})

    clone = http_app.post("/api/tasks/task-100/clone", json={"id": "task-copy"})
    fetched = http_app.get("/api/tasks/task-copy")

    assert clone.status_code == HTTPStatus.CREATED
    body = clone.json()
    assert body["status"] == "backlog"
    assert body["cloned_from"] == "task-100"
    assert fetched.json()["title"] == "Write E2 tests"


@pytest.mark.api
def test_no_timer_roundtrips_via_create_and_patch(http_app):
    """DF13 over HTTP: create carries the flag, PATCH flips it both ways."""
    created = http_app.post("/api/tasks", json={**_task_payload(), "no_timer": True})
    assert created.status_code == HTTPStatus.CREATED
    assert created.json()["no_timer"] is True

    patched = http_app.patch("/api/tasks/task-100", json={"no_timer": False})
    fetched = http_app.get("/api/tasks/task-100")

    assert patched.json()["no_timer"] is False
    assert fetched.json()["no_timer"] is False


@pytest.mark.api
def test_patch_recurrence_roundtrip_and_empty_days_rejected(http_app):
    """DF8 over HTTP: checkboxes save via PATCH; zero ticks must not pass."""
    http_app.post("/api/tasks", json=_task_payload())

    ok = http_app.patch(
        "/api/tasks/task-100",
        json={"recurrence": {"kind": "on_dates", "days": ["2026-09-09", "2026-09-11"]}},
    )
    fetched = http_app.get("/api/tasks/task-100")

    assert ok.status_code == HTTPStatus.OK
    assert ok.json()["recurrence"] == {
        "kind": "on_dates",
        "days": ["2026-09-09", "2026-09-11"],
    }
    assert fetched.json()["recurrence"]["kind"] == "on_dates"

    blank = http_app.patch(
        "/api/tasks/task-100", json={"recurrence": {"kind": "on_dates", "days": []}}
    )
    assert blank.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.api
def test_task_list_carries_blocks_done_progress(http_app):
    """DF10 over HTTP: GET /api/tasks ships the counted blocks per card."""
    http_app.post("/api/tasks", json=_task_payload())

    listed = http_app.get("/api/tasks").json()

    assert listed[0]["blocks_done"] == 0  # fresh card: nothing worked yet
    single = http_app.get("/api/tasks/task-100")
    assert single.json()["blocks_done"] is None  # detail view: not a board concern


@pytest.mark.api
def test_task_list_carries_last_worked_for_the_week_filter(http_app):
    """Filter batch over HTTP: the board scan carries the last worked day."""
    http_app.post("/api/tasks", json=_task_payload())

    listed = http_app.get("/api/tasks").json()

    assert listed[0]["last_worked"] is None  # fresh card: never worked
    body = http_app.get("/api/tasks/task-100").json()
    assert body["last_worked"] is None  # detail: same null discipline
