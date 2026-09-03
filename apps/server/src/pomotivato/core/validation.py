"""Validation rules for core models (spec 01 §7, V1..V11).

Each rule raises a spec-01 error subclass so the UI layer can branch on
error kind instead of parsing messages.
"""

from __future__ import annotations

from pomotivato.core.errors import (
    DayPlanValidationError,
    RecurrenceValidationError,
    ReviewValidationError,
    ScienceFieldRequiredError,
    SettingsValidationError,
    StatusTransitionError,
    TaskValidationError,
)
from pomotivato.core.models import (
    MAX_SECTOR,
    Daily,
    DayPlan,
    Once,
    Recurrence,
    Review,
    SessionSettings,
    Slot,
    Task,
    TaskStatus,
    WeeklyCount,
    WeeklyDays,
)
from pomotivato.core.science import recommended_start

TITLE_MAX_LEN = 200
_MINUTES_RANGE = range(1, 241)
_LONG_BREAK_EVERY_RANGE = range(2, 7)
_SCORE_RANGE = range(1, 6)

# V7 allowed kanban transitions; DONE -> DOING is rework (author spec).
_ALLOWED_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.BACKLOG: frozenset({TaskStatus.PLANNED, TaskStatus.ARCHIVED}),
    TaskStatus.PLANNED: frozenset({TaskStatus.DOING, TaskStatus.BACKLOG, TaskStatus.ARCHIVED}),
    TaskStatus.DOING: frozenset({TaskStatus.DONE, TaskStatus.PLANNED, TaskStatus.ARCHIVED}),
    TaskStatus.DONE: frozenset({TaskStatus.DOING}),
    TaskStatus.ARCHIVED: frozenset({TaskStatus.BACKLOG}),
}


def validate_task(task: Task) -> None:
    """Check V1 (title), V2 handled by enums at parse time, V3 (blocks)."""
    if not task.title.strip():
        msg = "title must not be empty"
        raise TaskValidationError(msg)
    if len(task.title) > TITLE_MAX_LEN:
        msg = f"title exceeds {TITLE_MAX_LEN} characters"
        raise TaskValidationError(msg)
    if task.estimate_blocks < 1:
        msg = "estimate_blocks must be >= 1"
        raise TaskValidationError(msg)


def validate_recurrence(rec: Recurrence) -> None:
    """Check V11 recurrence parameters."""
    match rec:
        case Once() | Daily():
            return
        case WeeklyDays(weekdays=days):
            if not days or not days <= frozenset(range(7)):
                msg = f"weekdays must be a non-empty subset of 0..6, got {sorted(days)}"
                raise RecurrenceValidationError(msg)
        case WeeklyCount(n=n, start=start):
            if not 1 <= n <= 6:
                msg = f"n must be 1..6, got {n}"
                raise RecurrenceValidationError(msg)
            # Sanity floor for serialized data; E2 enforces calendar bounds.
            if start.year < 2000:
                msg = f"unreasonable start date: {start}"
                raise RecurrenceValidationError(msg)


def validate_review(review: Review) -> None:
    """Check V4: score within 1..5."""
    if review.score not in _SCORE_RANGE:
        msg = f"score must be 1..5, got {review.score}"
        raise ReviewValidationError(msg)


def validate_settings(settings: SessionSettings) -> None:
    """Check V5: durations and long-break cadence ranges."""
    for name in ("work_min", "break_min", "long_break_min"):
        value = getattr(settings, name)
        if value not in _MINUTES_RANGE:
            msg = f"{name} must be 1..240, got {value}"
            raise SettingsValidationError(msg)
    if settings.long_break_every not in _LONG_BREAK_EVERY_RANGE:
        msg = f"long_break_every must be 2..6, got {settings.long_break_every}"
        raise SettingsValidationError(msg)


def validate_day_plan(plan: DayPlan, tasks: dict[str, Task]) -> None:
    """Check V9 (sector bounds/uniqueness) and V10 (chunk cap per task)."""
    if not plan.slots:
        msg = "day plan must have at least one slot"
        raise DayPlanValidationError(msg)
    if len(plan.slots) > MAX_SECTOR:
        msg = f"day plan exceeds {MAX_SECTOR} sectors"
        raise DayPlanValidationError(msg)
    sectors = [slot.sector for slot in plan.slots]
    if len(set(sectors)) != len(sectors):
        msg = f"duplicate sectors: {sectors}"
        raise DayPlanValidationError(msg)
    for slot in plan.slots:
        _validate_slot(slot, tasks)
    counts = _slot_counts(plan.slots)
    for task_id, used in counts.items():
        task = tasks[task_id]
        # Chunk composite: up to estimate_blocks slots the same day (spec V10).
        if used > max(task.estimate_blocks, 1):
            msg = f"task {task_id} uses {used} slots, max {task.estimate_blocks}"
            raise DayPlanValidationError(msg)


def _validate_slot(slot: Slot, tasks: dict[str, Task]) -> None:
    if not 1 <= slot.sector <= MAX_SECTOR:
        msg = f"sector must be 1..{MAX_SECTOR}, got {slot.sector}"
        raise DayPlanValidationError(msg)
    if slot.task_id not in tasks:
        msg = f"slot refers to unknown task {slot.task_id!r}"
        raise DayPlanValidationError(msg)


def _slot_counts(slots: tuple[Slot, ...]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for slot in slots:
        counts[slot.task_id] = counts.get(slot.task_id, 0) + 1
    return counts


def validate_status_transition(old: TaskStatus, new: TaskStatus) -> None:
    """Check V7 kanban status machine."""
    if new not in _ALLOWED_TRANSITIONS[old]:
        msg = f"illegal status transition {old.value} -> {new.value}"
        raise StatusTransitionError(msg)


def validate_planning_ready(task: Task, require_science_fields: bool) -> None:
    """V8: when_then gate for BACKLOG -> PLANNED, soft by default (§2.2#12)."""
    if require_science_fields and not (task.when_then or "").strip():
        msg = f"task {task.id!r} needs when_then to enter planning"
        raise ScienceFieldRequiredError(msg)


def validate_deadline_realism(task: Task) -> None:
    """V6: a deadline task must have enough runway (spec 01 §6.2/P3 link).

    recommended_start must not be earlier than creation day: if it is,
    the plan no longer fits and the user hears it at planning time, not
    at the missed deadline. Tasks without a deadline always pass.
    """
    if task.deadline is None:
        return
    start = recommended_start(task.deadline, task.estimate_blocks)
    if start < task.created_at.date():
        msg = (
            f"deadline {task.deadline} is unrealistic: {task.estimate_blocks} "
            f"blocks fit no earlier than {start}, task created "
            f"{task.created_at.date()}"
        )
        raise TaskValidationError(msg)
