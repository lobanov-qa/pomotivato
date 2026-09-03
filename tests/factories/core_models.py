"""Factories for core domain models (no hardcoded entity data in tests)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from itertools import count
from typing import Any

from pomotivato.core.models import (
    Daily,
    DayPlan,
    Once,
    Recurrence,
    RepetitionState,
    Review,
    Segment,
    SegmentPhase,
    Session,
    SessionSettings,
    SessionState,
    Slot,
    Task,
    TaskStatus,
    TaskType,
)

_counter = count(1)
DEFAULT_DAY = date(2026, 9, 3)
DEFAULT_MOMENT = datetime(2026, 9, 3, 9, 0, tzinfo=UTC)


def next_id(prefix: str = "id") -> str:
    """Return a unique synthetic identifier."""
    return f"{prefix}-{next(_counter)}"


def task_factory(**overrides: Any) -> Task:
    """Build a valid backlog task unless overridden."""
    args: dict[str, Any] = {
        "id": next_id("task"),
        "title": f"Task {next(_counter)}",
        "type": TaskType.NORMAL,
        "important": False,
        "urgent": False,
        "status": TaskStatus.BACKLOG,
        "estimate_blocks": 1,
        "recurrence": Once(),
        "created_at": DEFAULT_MOMENT,
    }
    args.update(overrides)
    return Task(**args)


def settings_factory(**overrides: Any) -> SessionSettings:
    args: dict[str, Any] = {
        "work_min": 25,
        "break_min": 5,
        "long_break_min": 15,
        "long_break_every": 4,
        "auto_start_next": True,
    }
    args.update(overrides)
    return SessionSettings(**args)


def slot_factory(**overrides: Any) -> Slot:
    args: dict[str, Any] = {"sector": 1, "task_id": next_id("task")}
    args.update(overrides)
    return Slot(**args)


def day_plan_factory(slots: tuple[Slot, ...] | None = None, **overrides: Any) -> DayPlan:
    args: dict[str, Any] = {
        "id": next_id("plan"),
        "date": DEFAULT_DAY,
        "slots": slots if slots is not None else (slot_factory(),),
    }
    args.update(overrides)
    return DayPlan(**args)


def review_factory(**overrides: Any) -> Review:
    args: dict[str, Any] = {"segment_id": next_id("seg"), "score": 4}
    args.update(overrides)
    return Review(**args)


def segment_factory(**overrides: Any) -> Segment:
    args: dict[str, Any] = {
        "id": next_id("seg"),
        "session_id": next_id("ses"),
        "phase": SegmentPhase.WORK,
        "planned_min": 25,
    }
    args.update(overrides)
    return Segment(**args)


def session_factory(**overrides: Any) -> Session:
    args: dict[str, Any] = {
        "id": next_id("ses"),
        "day_plan_id": next_id("plan"),
        "state": SessionState.IDLE,
        "settings": settings_factory(),
    }
    args.update(overrides)
    return Session(**args)


def repetition_factory(**overrides: Any) -> RepetitionState:
    args: dict[str, Any] = {
        "task_id": next_id("task"),
        "interval_idx": 0,
        "next_due": DEFAULT_DAY,
    }
    args.update(overrides)
    return RepetitionState(**args)


def daily_recurrence() -> Recurrence:
    return Daily()
