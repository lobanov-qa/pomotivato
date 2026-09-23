"""Response-schema helpers for the HTTP floor (author's school §6.6)."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError

from pomotivato.api.schemas import DayPlanDto, SessionSettingsDto, TaskDto

__all__ = [
    "TaskDto",
    "DayPlanDto",
    "SessionSettingsDto",
    "assert_detail_code",
    "put_in_work",
    "validate_as",
]


def assert_detail_code(response: TestClient, code: str) -> None:
    """Check the stable error envelope {"detail": {"code", "message"}}."""
    body: dict[str, Any] = response.json()
    assert body["detail"]["code"] == code, body


def put_in_work(client: TestClient, *task_ids: str) -> None:
    """Move cards to «В работе» through the funnel (V7 has no backlog shortcut).

    Only the doing column backs a running dial (author's law 23.09), so the
    fixtures must walk the same path the UI does: backlog -> planned -> doing.
    """
    for task_id in task_ids:
        for status in ("planned", "doing"):
            response = client.post(f"/api/tasks/{task_id}/status", json={"to": status})
            assert response.status_code == HTTPStatus.OK, response.json()


def validate_as(schema: type[BaseModel], payload: object) -> BaseModel:
    """Return payload validated by schema; a schema mismatch is a failure."""
    try:
        return schema.model_validate(payload)
    except ValidationError as err:
        raise AssertionError(f"response violates {schema.__name__}: {err}") from err
