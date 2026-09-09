"""Validation rules for core models (spec 01 §7, V1..V11).

Each rule raises a spec-01 error subclass so the UI layer can branch on
error kind instead of parsing messages.
"""

from __future__ import annotations

from datetime import time

from pomotivato.core.errors import (
    DayPlanValidationError,
    RecurrenceValidationError,
    ReviewValidationError,
    ScienceFieldRequiredError,
    SettingsValidationError,
    StatusTransitionError,
    TaskValidationError,
    ValidationError,
)
from pomotivato.core.models import (
    MAX_ON_DATES,
    MAX_SECTOR,
    Daily,
    DayPlan,
    Once,
    OnDates,
    Recurrence,
    Review,
    SessionSettings,
    Slot,
    Sprint,
    SprintStatus,
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
# E4b modes (spec 01 v0.4): V12/V13 bounds.
_WARMUP_RANGE = range(0, 31)
_SPECIAL_DURATION_RANGE = range(5, 121)
_SPECIAL_LABEL_MAX_LEN = 40
MAX_SPECIAL_BREAKS = 3
# Sprints (spec 05 §3.10 / ADR-0003 p.3): V14/V15 bounds.
SPRINT_MAX_DAYS = 14
SPRINT_TEXT_MAX_LEN = 200

# V15 allowed sprint transitions: one-way, completed is terminal.
_SPRINT_TRANSITIONS: dict[SprintStatus, frozenset[SprintStatus]] = {
    SprintStatus.PLANNED: frozenset({SprintStatus.ACTIVE}),
    SprintStatus.ACTIVE: frozenset({SprintStatus.COMPLETED}),
    SprintStatus.COMPLETED: frozenset(),
}

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
    # V11 rides every task write (create/PATCH/clone): a recurrence that
    # cannot expand must not reach storage to surprise the week view.
    validate_recurrence(task.recurrence)


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
        case OnDates(days=ticked):
            # DF8: ticked calendar days — at least one, never more than a
            # sprint (V14 cap shared with sprints). An empty set is the
            # UI's "uncheck all" and must arrive as Once, not here.
            if not 1 <= len(ticked) <= MAX_ON_DATES:
                msg = f"on_dates must hold 1..{MAX_ON_DATES} days, got {len(ticked)}"
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
    # V12/V13 (spec 01 v0.4, E4b modes).
    if settings.warmup_min not in _WARMUP_RANGE:
        msg = f"warmup_min must be 0..30, got {settings.warmup_min}"
        raise SettingsValidationError(msg)
    if len(settings.special_breaks) > MAX_SPECIAL_BREAKS:
        msg = f"at most {MAX_SPECIAL_BREAKS} special breaks, got {len(settings.special_breaks)}"
        raise SettingsValidationError(msg)
    seen_times: set[time] = set()
    for brk in settings.special_breaks:
        if brk.duration_min not in _SPECIAL_DURATION_RANGE:
            msg = f"special break duration must be 5..120, got {brk.duration_min}"
            raise SettingsValidationError(msg)
        if len(brk.label) > _SPECIAL_LABEL_MAX_LEN:
            msg = f"special break label exceeds {_SPECIAL_LABEL_MAX_LEN} chars"
            raise SettingsValidationError(msg)
        if brk.at in seen_times:
            msg = f"duplicate special break time: {brk.at}"
            raise SettingsValidationError(msg)
        seen_times.add(brk.at)


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


def validate_sprint(sprint: Sprint) -> None:
    """Check V14: period length 1..14 days, number ≥1, optional fields sized."""
    if sprint.number < 1:
        msg = f"sprint number must be >= 1, got {sprint.number}"
        raise ValidationError(msg)
    length = (sprint.end_date - sprint.start_date).days + 1
    if not 1 <= length <= SPRINT_MAX_DAYS:
        msg = f"sprint must span 1..{SPRINT_MAX_DAYS} days, got {length}"
        raise ValidationError(msg)
    for field_name in ("name", "goal", "done_criteria"):
        value = getattr(sprint, field_name)
        if value is not None and len(value) > SPRINT_TEXT_MAX_LEN:
            msg = f"{field_name} exceeds {SPRINT_TEXT_MAX_LEN} characters"
            raise ValidationError(msg)


def validate_sprint_transition(old: SprintStatus, new: SprintStatus) -> None:
    """Check V15: planned->active->completed, no shortcuts, no re-open."""
    if new not in _SPRINT_TRANSITIONS[old]:
        msg = f"illegal sprint status transition {old.value} -> {new.value}"
        raise ValidationError(msg)


def validate_planning_ready(task: Task, require_science_fields: bool) -> None:
    """V8: when_then gate for BACKLOG -> PLANNED, soft by default (§2.2#12).

    DF13 (spec 06): board-only errands are exempt — the gate exists to
    feed the science report, and a no-timer task produces no report.
    """
    if task.no_timer:
        return
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
