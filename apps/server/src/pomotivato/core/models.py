"""Domain models of the pure core (spec 01 §2).

Plain frozen dataclasses: no persistence, no HTTP, no asyncio. Field sets
mirror master-plan §9; the full DB row shape is finalized in E2 models.
to_dict/from_dict are the canonical serialization used by the round-trip
tests and later by day_plans.slots_json / settings_json in E2.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pomotivato.core.clock import as_utc
from pomotivato.core.errors import ValidationError


class TaskStatus(StrEnum):
    BACKLOG = "backlog"
    PLANNED = "planned"
    DOING = "doing"
    DONE = "done"
    ARCHIVED = "archived"


class TaskType(StrEnum):
    NORMAL = "normal"
    STUDY = "study"
    HABIT = "habit"


class SegmentPhase(StrEnum):
    WORK = "work"
    BREAK = "break"
    LONG_BREAK = "long_break"


class SegmentStatus(StrEnum):
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    SKIPPED = "skipped"


class SessionState(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    STOPPED = "stopped"


@dataclass(frozen=True, slots=True)
class Once:
    """Single-run task: lands in one slot manually, nothing expands."""


@dataclass(frozen=True, slots=True)
class Daily:
    """Repeats every day (habit loop baseline)."""


@dataclass(frozen=True, slots=True)
class WeeklyDays:
    """Repeats on the given weekdays (ISO: Monday=0 ... Sunday=6)."""

    weekdays: frozenset[int]


@dataclass(frozen=True, slots=True)
class WeeklyCount:
    """Repeats n times per ISO week, starting from a given day."""

    n: int
    start: date


# A task repeats in exactly one of these modes (spec 01 §2).
Recurrence = Once | Daily | WeeklyDays | WeeklyCount

# Dial has 1..12 sectors by default (master §2.2#3); 6 is a UI default,
# the core always allows the full range.
MAX_SECTOR = 12


@dataclass(frozen=True, slots=True)
class Slot:
    """One dial sector (1..12) of the day occupied by one task."""

    sector: int
    task_id: str


@dataclass(frozen=True, slots=True)
class Task:
    id: str
    title: str
    type: TaskType
    important: bool
    urgent: bool
    status: TaskStatus
    estimate_blocks: int
    recurrence: Recurrence
    created_at: datetime
    deadline: date | None = None
    parent_id: str | None = None
    when_then: str | None = None
    done_criteria: str | None = None
    benefit: str | None = None


@dataclass(frozen=True, slots=True)
class DayPlan:
    id: str
    date: date
    slots: tuple[Slot, ...]


@dataclass(frozen=True, slots=True)
class SessionSettings:
    work_min: int = 25
    break_min: int = 5
    long_break_min: int = 15
    long_break_every: int = 4
    auto_start_next: bool = True


@dataclass(frozen=True, slots=True)
class Segment:
    id: str
    session_id: str
    phase: SegmentPhase
    planned_min: int
    task_id: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    status: SegmentStatus | None = None


@dataclass(frozen=True, slots=True)
class Session:
    id: str
    day_plan_id: str
    state: SessionState
    settings: SessionSettings
    started_at: datetime | None = None
    stop_reason: str | None = None


@dataclass(frozen=True, slots=True)
class Review:
    segment_id: str
    score: int
    comment: str | None = None
    recall_notes: str | None = None
    reward: str | None = None


@dataclass(frozen=True, slots=True)
class RepetitionState:
    task_id: str
    interval_idx: int
    next_due: date


def to_dict(obj: Any) -> dict[str, Any]:
    """Serialize a core model to JSON-friendly plain values.

    Enums become their string value, dates/datetimes ISO strings, sets
    sorted lists. Round-trips with the matching *_from_dict below.
    """
    return dict(_jsonify(asdict(obj)))


def _jsonify(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, date | datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {k: _jsonify(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonify(v) for v in value]
    if isinstance(value, set | frozenset):
        return sorted(_jsonify(v) for v in value)
    return value


def _require(data: Mapping[str, Any], key: str) -> Any:
    if key not in data:
        msg = f"missing field {key!r}"
        raise ValidationError(msg)
    return data[key]


def task_to_dict(task: Task) -> dict[str, Any]:
    """Serialize a Task, tagging its nested recurrence variant."""
    data = to_dict(task)
    data["recurrence"] = recurrence_to_dict(task.recurrence)
    return data


def _enum(enum_cls: type[StrEnum], raw: Any, field_name: str) -> Any:
    try:
        return enum_cls(raw)
    except ValueError as err:
        msg = f"unknown {field_name}: {raw!r}"
        raise ValidationError(msg) from err


def _parse_date(raw: Any, field_name: str) -> date:
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    try:
        return date.fromisoformat(str(raw))
    except ValueError as err:
        msg = f"bad {field_name} date: {raw!r}"
        raise ValidationError(msg) from err


def _parse_dt(raw: Any, field_name: str) -> datetime:
    try:
        parsed = raw if isinstance(raw, datetime) else datetime.fromisoformat(str(raw))
        return as_utc(parsed)
    except ValueError as err:
        msg = f"bad {field_name} datetime: {raw!r} ({err})"
        raise ValidationError(msg) from err


def _opt(raw: Any, fn: Any) -> Any:
    return None if raw is None else fn(raw)


_RECURRENCE_TAGS = {"once", "daily", "weekly_days", "weekly_count"}


def recurrence_to_dict(rec: Recurrence) -> dict[str, Any]:
    """Serialize a recurrence variant with an explicit type tag."""
    data: dict[str, Any] = _jsonify(asdict(rec))
    tag_map: dict[type, str] = {
        Once: "once",
        Daily: "daily",
        WeeklyDays: "weekly_days",
        WeeklyCount: "weekly_count",
    }
    data["kind"] = tag_map[type(rec)]
    return data


def recurrence_from_dict(data: Mapping[str, Any]) -> Recurrence:
    """Parse back recurrence_to_dict output."""
    kind = _require(data, "kind")
    if kind not in _RECURRENCE_TAGS:
        msg = f"unknown recurrence kind: {kind!r}"
        raise ValidationError(msg)
    if kind == "once":
        return Once()
    if kind == "daily":
        return Daily()
    if kind == "weekly_days":
        days = frozenset(_require(data, "weekdays"))
        return WeeklyDays(days)
    return WeeklyCount(
        n=int(_require(data, "n")),
        start=_parse_date(_require(data, "start"), "start"),
    )


def task_from_dict(data: Mapping[str, Any]) -> Task:
    """Parse a Task (V2-style enum errors raise ValidationError)."""
    return Task(
        id=str(_require(data, "id")),
        title=str(_require(data, "title")),
        type=_enum(TaskType, _require(data, "type"), "type"),
        important=bool(_require(data, "important")),
        urgent=bool(_require(data, "urgent")),
        status=_enum(TaskStatus, _require(data, "status"), "status"),
        estimate_blocks=int(_require(data, "estimate_blocks")),
        recurrence=recurrence_from_dict(_require(data, "recurrence")),
        created_at=_parse_dt(_require(data, "created_at"), "created_at"),
        deadline=_opt(data.get("deadline"), lambda r: _parse_date(r, "deadline")),
        parent_id=data.get("parent_id"),
        when_then=data.get("when_then"),
        done_criteria=data.get("done_criteria"),
        benefit=data.get("benefit"),
    )


def slot_from_dict(data: Mapping[str, Any]) -> Slot:
    return Slot(sector=int(_require(data, "sector")), task_id=str(_require(data, "task_id")))


def day_plan_from_dict(data: Mapping[str, Any]) -> DayPlan:
    raw_slots = _require(data, "slots")
    return DayPlan(
        id=str(_require(data, "id")),
        date=_parse_date(_require(data, "date"), "date"),
        slots=tuple(slot_from_dict(s) for s in raw_slots),
    )


def session_settings_from_dict(data: Mapping[str, Any]) -> SessionSettings:
    return SessionSettings(
        work_min=int(_require(data, "work_min")),
        break_min=int(_require(data, "break_min")),
        long_break_min=int(_require(data, "long_break_min")),
        long_break_every=int(_require(data, "long_break_every")),
        auto_start_next=bool(_require(data, "auto_start_next")),
    )


def segment_from_dict(data: Mapping[str, Any]) -> Segment:
    raw_status = data.get("status")
    return Segment(
        id=str(_require(data, "id")),
        session_id=str(_require(data, "session_id")),
        phase=_enum(SegmentPhase, _require(data, "phase"), "phase"),
        planned_min=int(_require(data, "planned_min")),
        task_id=data.get("task_id"),
        started_at=_opt(data.get("started_at"), lambda r: _parse_dt(r, "started_at")),
        ended_at=_opt(data.get("ended_at"), lambda r: _parse_dt(r, "ended_at")),
        status=_opt(raw_status, lambda r: _enum(SegmentStatus, r, "status")),
    )


def session_from_dict(data: Mapping[str, Any]) -> Session:
    return Session(
        id=str(_require(data, "id")),
        day_plan_id=str(_require(data, "day_plan_id")),
        state=_enum(SessionState, _require(data, "state"), "state"),
        settings=session_settings_from_dict(_require(data, "settings")),
        started_at=_opt(data.get("started_at"), lambda r: _parse_dt(r, "started_at")),
        stop_reason=data.get("stop_reason"),
    )


def review_from_dict(data: Mapping[str, Any]) -> Review:
    return Review(
        segment_id=str(_require(data, "segment_id")),
        score=int(_require(data, "score")),
        comment=data.get("comment"),
        recall_notes=data.get("recall_notes"),
        reward=data.get("reward"),
    )


def repetition_state_from_dict(data: Mapping[str, Any]) -> RepetitionState:
    return RepetitionState(
        task_id=str(_require(data, "task_id")),
        interval_idx=int(_require(data, "interval_idx")),
        next_due=_parse_date(_require(data, "next_due"), "next_due"),
    )
