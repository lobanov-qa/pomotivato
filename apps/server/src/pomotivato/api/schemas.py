"""Transport DTOs: HTTP JSON shapes <-> core dataclasses (spec 02 §5).

Pydantic here is transport only: it parses/canonicalizes strings into core
types; every business rule stays in pomotivato.core validators (DRY).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from pomotivato.core.models import (
    DayPlan,
    SessionSettings,
    Slot,
    Task,
    TaskStatus,
    TaskType,
    recurrence_from_dict,
    recurrence_to_dict,
    to_dict,
)


class RecurrenceDto(BaseModel):
    """Tagged recurrence variant, identical to core recurrence_to_dict."""

    kind: str
    weekdays: list[int] | None = None
    n: int | None = None
    start: date | None = None


class TaskCreateDto(BaseModel):
    id: str
    title: str
    type: TaskType = TaskType.NORMAL
    important: bool = False
    urgent: bool = False
    estimate_blocks: int = 1
    recurrence: RecurrenceDto = RecurrenceDto(kind="once")
    deadline: date | None = None
    parent_id: str | None = None
    when_then: str | None = None
    done_criteria: str | None = None
    benefit: str | None = None

    def to_core(self, created_at: datetime) -> Task:
        return Task(
            id=self.id,
            title=self.title,
            type=self.type,
            important=self.important,
            urgent=self.urgent,
            status=TaskStatus.BACKLOG,
            estimate_blocks=self.estimate_blocks,
            recurrence=recurrence_from_dict(self.recurrence.model_dump(exclude_none=True)),
            created_at=created_at,
            deadline=self.deadline,
            parent_id=self.parent_id,
            when_then=self.when_then,
            done_criteria=self.done_criteria,
            benefit=self.benefit,
        )


class TaskPatchDto(BaseModel):
    """Partial update; unknown keys rejected, status has its own route."""

    title: str | None = None
    type: TaskType | None = None
    important: bool | None = None
    urgent: bool | None = None
    estimate_blocks: int | None = None
    deadline: date | None = None
    parent_id: str | None = None
    when_then: str | None = None
    done_criteria: str | None = None
    benefit: str | None = None

    def changes(self) -> dict[str, Any]:
        # exclude_unset: an explicit null clears a field, an absent key
        # leaves it untouched (PATCH semantics, spec 02 §5).
        return self.model_dump(exclude_unset=True)


class TaskDto(BaseModel):
    id: str
    title: str
    type: str
    important: bool
    urgent: bool
    status: str
    estimate_blocks: int
    recurrence: dict[str, Any]
    deadline: str | None
    parent_id: str | None
    when_then: str | None
    done_criteria: str | None
    benefit: str | None
    created_at: str

    @classmethod
    def from_core(cls, task: Task) -> TaskDto:
        data = to_dict(task)
        # to_dict flattens recurrence without its kind tag; restore it.
        data["recurrence"] = recurrence_to_dict(task.recurrence)
        return cls(**data)


class SlotDto(BaseModel):
    sector: int
    task_id: str


class DayPlanDto(BaseModel):
    id: str
    date: date
    slots: list[SlotDto]

    def to_core(self) -> DayPlan:
        return DayPlan(
            id=self.id,
            date=self.date,
            slots=tuple(Slot(sector=s.sector, task_id=s.task_id) for s in self.slots),
        )

    @classmethod
    def from_core(cls, plan: DayPlan) -> DayPlanDto:
        return cls(id=plan.id, date=plan.date, slots=[SlotDto(**to_dict(s)) for s in plan.slots])


class MoveSlotDto(BaseModel):
    # Wire names are `from`/`to`; Python needs aliases around the keyword.
    model_config = ConfigDict(populate_by_name=True)

    from_pos: int = Field(alias="from")
    to_pos: int = Field(alias="to")

    @field_validator("from_pos", "to_pos")
    @classmethod
    def _positive(cls, value: int) -> int:
        if value < 1:
            msg = "slot positions are 1-based"
            raise ValueError(msg)
        return value


class SetStatusDto(BaseModel):
    to: TaskStatus


class SessionSettingsDto(BaseModel):
    work_min: int = 25
    break_min: int = 5
    long_break_min: int = 15
    long_break_every: int = 4
    auto_start_next: bool = True

    def to_core(self) -> SessionSettings:
        return SessionSettings(
            work_min=self.work_min,
            break_min=self.break_min,
            long_break_min=self.long_break_min,
            long_break_every=self.long_break_every,
            auto_start_next=self.auto_start_next,
        )

    @classmethod
    def from_core(cls, settings: SessionSettings) -> SessionSettingsDto:
        return cls(**to_dict(settings))
