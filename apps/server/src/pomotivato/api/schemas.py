"""Transport DTOs: HTTP JSON shapes <-> core dataclasses (spec 02 §5).

Pydantic here is transport only: it parses/canonicalizes strings into core
types; every business rule stays in pomotivato.core validators (DRY).
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from pomotivato.core.models import (
    DayPlan,
    Review,
    Segment,
    SessionSettings,
    Slot,
    SpecialBreak,
    Sprint,
    Task,
    TaskStatus,
    TaskType,
    recurrence_from_dict,
    recurrence_to_dict,
    to_dict,
)
from pomotivato.services.session_service import SessionView


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
    cloned_from: str | None = None

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
            cloned_from=self.cloned_from,
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
    cloned_from: str | None
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


class TaskCloneDto(BaseModel):
    """DF12: the id the client generates for the new copy (POST idiom)."""

    id: str


class SessionCreateDto(BaseModel):
    day_plan_id: str
    settings: SessionSettingsDto | None = None


class SegmentDto(BaseModel):
    id: str
    session_id: str
    phase: str
    planned_min: int
    task_id: str | None
    started_at: str | None
    ended_at: str | None
    status: str | None
    # E4b special breaks: label of a SPECIAL_BREAK segment, None otherwise
    # (additive mirror of core Segment).
    break_label: str | None = None

    @classmethod
    def from_core(cls, segment: Segment) -> SegmentDto:
        return cls(**to_dict(segment))


class ReviewDto(BaseModel):
    segment_id: str
    score: int
    comment: str | None = None
    recall_notes: str | None = None
    reward: str | None = None

    @classmethod
    def from_core(cls, review: Review) -> ReviewDto:
        return cls(**to_dict(review))


class ReviewCreateDto(BaseModel):
    segment_id: str
    score: int
    comment: str | None = None
    # E4b payload (spec 05 §3.7-3.8): active-recall notes, habit reward.
    recall_notes: str | None = None
    reward: str | None = None


class SessionDto(BaseModel):
    """View of one session: FSM state + timeline + reviews (spec 02 §5 GET)."""

    id: str
    day_plan_id: str
    state: str
    started_at: str | None
    stop_reason: str | None
    phase: str | None
    remaining_sec: int
    phase_ends_at: str | None
    average_score: float | None
    settings: SessionSettingsDto
    timeline: list[SegmentDto]
    reviews: list[ReviewDto]
    # Frozen slot snapshot (spec 01 v0.3): the dial's sector count and per-
    # sector task identity. None marks pre-E3 legacy rows (additive field).
    slots: list[SlotDto] | None = None

    @classmethod
    def from_view(cls, view: SessionView) -> SessionDto:
        return cls(
            id=view.session.id,
            day_plan_id=view.session.day_plan_id,
            state=view.session.state.value,
            started_at=view.session.started_at.isoformat() if view.session.started_at else None,
            stop_reason=view.session.stop_reason,
            phase=view.phase,
            remaining_sec=view.remaining_sec,
            phase_ends_at=view.ends_at.isoformat() if view.ends_at else None,
            average_score=view.average_score,
            settings=SessionSettingsDto.from_core(view.session.settings),
            timeline=[SegmentDto.from_core(seg) for seg in view.timeline],
            reviews=[ReviewDto.from_core(review) for review in view.reviews],
            slots=(
                [SlotDto(**to_dict(s)) for s in view.session.slots]
                if view.session.slots is not None
                else None
            ),
        )


class SpecialBreakDto(BaseModel):
    """One clock-anchored break row (spec 05 §3.3; wire form HH:MM, same
    canonical as core _jsonify, so settings round-trips are byte-stable)."""

    at: time
    duration_min: int = Field(ge=5, le=120)
    label: str = ""

    @field_serializer("at")
    def _serialize_at(self, value: time) -> str:
        return value.isoformat(timespec="minutes")


class SessionSettingsDto(BaseModel):
    work_min: int = 25
    break_min: int = 5
    long_break_min: int = 15
    long_break_every: int = 4
    auto_start_next: bool = True
    # E4b modes (spec 01 v0.4) — additive, defaults mirror core.
    strict_mode: bool = False
    warmup_min: int = Field(default=0, ge=0, le=30)
    special_breaks: list[SpecialBreakDto] = Field(default_factory=list)

    def to_core(self) -> SessionSettings:
        return SessionSettings(
            work_min=self.work_min,
            break_min=self.break_min,
            long_break_min=self.long_break_min,
            long_break_every=self.long_break_every,
            auto_start_next=self.auto_start_next,
            strict_mode=self.strict_mode,
            warmup_min=self.warmup_min,
            special_breaks=tuple(
                SpecialBreak(at=b.at, duration_min=b.duration_min, label=b.label)
                for b in self.special_breaks
            ),
        )

    @classmethod
    def from_core(cls, settings: SessionSettings) -> SessionSettingsDto:
        return cls(**to_dict(settings))


ThemeName = Literal["auto", "light", "dark"]


class UiSettingsDto(BaseModel):
    """UI-only settings (spec 03 §5, ⚑ Q3/Q9): in-work capacity + theme
    + the V8 science-fields gate (spec 05 §3.1 — the toggle is ui-truth)
    + the DF6 wet-hints ring switch."""

    max_in_work: int = Field(default=6, ge=1, le=12)
    theme: ThemeName = "auto"
    require_science_fields: bool = False
    wet_hints: bool = True


class SettingsBundleDto(BaseModel):
    """GET /api/settings dictionary (spec 03 §5): every key in one read."""

    session: SessionSettingsDto
    ui: UiSettingsDto


class StatusDto(BaseModel):
    """Flat script contract for GET /api/status (spec 03 §5; fields are
    additive — removal would be a breaking change)."""

    active: bool
    session_id: str | None = None
    state: str | None = None
    phase: str | None = None
    remaining_sec: int | None = None
    server_now: str
    date: str


class DailySummaryDto(BaseModel):
    """Projection of one day: counts come from persisted FSM rows only."""

    date: str
    blocks_done: int
    blocks_planned: int
    focus_min: int
    average_score: float | None
    reviews_count: int
    tasks_done: int


class SprintCreateDto(BaseModel):
    """POST /api/sprints body (spec 05 §3.10): number is server-assigned."""

    name: str | None = None
    goal: str | None = None
    done_criteria: str | None = None
    start_date: date
    end_date: date


class SprintPatchDto(BaseModel):
    """PATCH /api/sprints/{id}: texts/period/status; number and id immutable."""

    name: str | None = None
    goal: str | None = None
    done_criteria: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    status: Literal["planned", "active", "completed"] | None = None

    def changes(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True)


class SprintDto(BaseModel):
    id: str
    number: int
    name: str | None
    start_date: str
    end_date: str
    goal: str | None
    done_criteria: str | None
    status: str

    @classmethod
    def from_core(cls, sprint: Sprint) -> SprintDto:
        return cls(**to_dict(sprint))


class DayPlanAddDto(BaseModel):
    """POST /api/day-plans/{date}/add body (spec 05 §3.8): the chunk source."""

    task_id: str


class AddResultDto(BaseModel):
    """Mutation outcome: the honest new plan + who got in / squeezed out.

    skipped is data, not an error (GWT-A3): a full day says so in 200,
    the week screen renders it — no silent loss.
    """

    plan: DayPlanDto
    added: list[str]
    skipped: list[str]


class HintDto(BaseModel):
    """Server computes kind+params only; RU/EN text is the dictionary's job."""

    kind: str
    params: dict[str, str | int] = Field(default_factory=dict)


class FrogDto(BaseModel):
    """Server-computed "eat the frog" candidate id (spec 05 §3.9): the
    kanban badge renders it, the client never re-implements the rule."""

    task_id: str | None = None


class RepetitionDueDto(BaseModel):
    """One due row of the spaced-repetition queue (spec 05 §3.7)."""

    task_id: str
    title: str
    interval_idx: int
    next_due: str
    overdue_days: int
