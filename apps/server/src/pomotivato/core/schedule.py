"""Day scheduling over pure dates: recurrence expansion and slot reordering.

expand_recurrence answers "which days in [date_from, date_to] does this
task repeat on?" — the materialization behind the calendar/week screen
(ADR-0003) and sprint views (a sprint is just an arbitrary date range).

move_slot is the single editing primitive for "task #2 of 6" ordering:
the UI drags, this function reorders (insert semantics, chunked tasks
travel as one block) and densely renumbers sectors 1..N. Running
sessions are untouched — SessionFSM snapshotted the plan at start().
"""

from __future__ import annotations

from datetime import date, timedelta

from pomotivato.core.errors import DayPlanValidationError, RecurrenceValidationError
from pomotivato.core.models import (
    Daily,
    DayPlan,
    Once,
    Recurrence,
    Slot,
    WeeklyCount,
    WeeklyDays,
)


def expand_recurrence(recurrence: Recurrence, date_from: date, date_to: date) -> tuple[date, ...]:
    """Materialize repeat days in an inclusive range (sorted, deduped).

    Once never expands: single-run tasks land in one slot manually.
    Empty range (date_from > date_to) yields () rather than an error —
    browsing a past sprint must not raise.
    """
    if date_to < date_from:
        return ()
    match recurrence:
        case Once():
            return ()
        case Daily():
            return _days_in_range(date_from, date_to)
        case WeeklyDays(weekdays=days):
            _validate_weekday_mask(days)
            return tuple(d for d in _days_in_range(date_from, date_to) if d.weekday() in days)
        case WeeklyCount(n=n, start=start):
            return _expand_weekly_count(n, start, date_from, date_to)


def _validate_weekday_mask(days: frozenset[int]) -> None:
    if not days or not days <= frozenset(range(7)):
        msg = f"weekdays must be a non-empty subset of 0..6, got {sorted(days)}"
        raise RecurrenceValidationError(msg)


def _days_in_range(date_from: date, date_to: date) -> tuple[date, ...]:
    total = (date_to - date_from).days + 1
    return tuple(date_from + timedelta(days=i) for i in range(total))


def _expand_weekly_count(n: int, start: date, date_from: date, date_to: date) -> tuple[date, ...]:
    """Up to n occurrences per ISO week, earliest days first, from `start`."""
    if not 1 <= n <= 6:
        msg = f"n must be 1..6, got {n}"
        raise RecurrenceValidationError(msg)
    picked: list[date] = []
    per_week: dict[tuple[int, int], int] = {}
    for day in _days_in_range(date_from, date_to):
        if day < start:
            continue
        iso = day.isocalendar()
        week = (iso.year, iso.week)
        if per_week.get(week, 0) < n:
            picked.append(day)
            per_week[week] = per_week.get(week, 0) + 1
    return tuple(picked)


def move_slot(plan: DayPlan, pos_from: int, pos_to: int) -> DayPlan:
    """Reorder the task at 1-based position pos_from to pos_to (pure).

    Positions count occupied slots ordered by sector. A task holding
    several slots (composite chunk) moves as one block keeping its
    internal order; the result is densely renumbered to sectors 1..N.
    Returns the same object when nothing moves (idempotent no-op).
    """
    ordered = sorted(plan.slots, key=lambda s: s.sector)
    size = len(ordered)
    if not 1 <= pos_from <= size or not 1 <= pos_to <= size:
        msg = f"positions must be 1..{size}, got {pos_from}->{pos_to}"
        raise DayPlanValidationError(msg)
    if pos_from == pos_to:
        return plan

    moved_task = ordered[pos_from - 1].task_id
    block = [slot for slot in ordered if slot.task_id == moved_task]
    rest = [slot for slot in ordered if slot.task_id != moved_task]
    insert_at = min(pos_to, len(rest) + 1) - 1
    result = [*rest[:insert_at], *block, *rest[insert_at:]]
    renumbered = tuple(
        Slot(sector=index + 1, task_id=slot.task_id) for index, slot in enumerate(result)
    )
    return DayPlan(id=plan.id, date=plan.date, slots=renumbered)
