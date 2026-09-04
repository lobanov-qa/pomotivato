"""Response-schema helpers for the HTTP floor (author's school §6.6)."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError

from pomotivato.api.schemas import DayPlanDto, SessionSettingsDto, TaskDto

__all__ = ["TaskDto", "DayPlanDto", "SessionSettingsDto", "assert_detail_code", "validate_as"]


def assert_detail_code(response: TestClient, code: str) -> None:
    """Check the stable error envelope {"detail": {"code", "message"}}."""
    body: dict[str, Any] = response.json()
    assert body["detail"]["code"] == code, body


def validate_as(schema: type[BaseModel], payload: object) -> BaseModel:
    """Return payload validated by schema; a schema mismatch is a failure."""
    try:
        return schema.model_validate(payload)
    except ValidationError as err:
        raise AssertionError(f"response violates {schema.__name__}: {err}") from err
