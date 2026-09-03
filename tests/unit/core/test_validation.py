"""Unit tests for validation rules V1..V11 (spec 01 §7; V6 ships with science)."""

from __future__ import annotations

from datetime import date

import pytest

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
    Daily,
    DayPlan,
    Once,
    Slot,
    TaskStatus,
    WeeklyCount,
    WeeklyDays,
)
from pomotivato.core.validation import (
    validate_day_plan,
    validate_planning_ready,
    validate_recurrence,
    validate_review,
    validate_settings,
    validate_status_transition,
    validate_task,
)
from tests.factories.core_models import (
    review_factory,
    settings_factory,
    slot_factory,
    task_factory,
)


def _plan(*slots: Slot) -> DayPlan:
    return DayPlan(id="plan-under-test", date=date(2026, 9, 3), slots=tuple(slots))


@pytest.mark.unit
def test_task_is_valid_when_fields_in_range():
    validate_task(task_factory())


@pytest.mark.unit
@pytest.mark.parametrize("title", ["", "   ", "\t\n"], ids=["empty", "spaces", "whitespace"])
def test_task_raises_when_title_blank(title):
    with pytest.raises(TaskValidationError, match="must not be empty"):
        validate_task(task_factory(title=title))


@pytest.mark.unit
def test_task_raises_when_title_too_long():
    with pytest.raises(TaskValidationError, match="exceeds 200"):
        validate_task(task_factory(title="x" * 201))


@pytest.mark.unit
def test_task_is_valid_when_title_at_boundary():
    validate_task(task_factory(title="x" * 200))


@pytest.mark.unit
@pytest.mark.parametrize("blocks", [0, -3])
def test_task_raises_when_estimate_blocks_below_one(blocks):
    with pytest.raises(TaskValidationError, match="estimate_blocks"):
        validate_task(task_factory(estimate_blocks=blocks))


@pytest.mark.unit
@pytest.mark.parametrize(
    "rec",
    [Once(), Daily(), WeeklyDays(frozenset({0, 1, 2}))],
    ids=["once", "daily", "weekly_days"],
)
def test_recurrence_is_valid_when_within_rules(rec):
    validate_recurrence(rec)


@pytest.mark.unit
@pytest.mark.parametrize(
    "days",
    [frozenset(), frozenset({7}), frozenset({-1, 2})],
    ids=["empty", "weekday_7", "negative"],
)
def test_weekly_days_raises_when_weekday_mask_invalid(days):
    with pytest.raises(RecurrenceValidationError, match="weekdays"):
        validate_recurrence(WeeklyDays(days))


@pytest.mark.unit
@pytest.mark.parametrize("n", [0, 7, -1])
def test_weekly_count_raises_when_n_out_of_range(n):
    with pytest.raises(RecurrenceValidationError, match=r"n must be 1\.\.6"):
        validate_recurrence(WeeklyCount(n=n, start=date(2026, 9, 1)))


@pytest.mark.unit
def test_weekly_count_raises_when_start_is_unreasonable():
    with pytest.raises(RecurrenceValidationError, match="unreasonable start"):
        validate_recurrence(WeeklyCount(n=3, start=date(1999, 1, 1)))


@pytest.mark.unit
@pytest.mark.parametrize(
    "score",
    [0, 1, 5, 6, -1],
    ids=["zero-bad", "one-ok", "five-ok", "six-bad", "neg-bad"],
)
def test_review_score_gate(score):
    review = review_factory(score=score)
    if score in (1, 5):
        validate_review(review)
    else:
        with pytest.raises(ReviewValidationError, match="score must be 1..5"):
            validate_review(review)


@pytest.mark.unit
def test_settings_are_valid_at_defaults():
    validate_settings(settings_factory())


@pytest.mark.unit
@pytest.mark.parametrize(
    ("field", "value"),
    [("work_min", 0), ("work_min", 241), ("break_min", -5), ("long_break_min", 999)],
)
def test_settings_raise_when_minutes_out_of_range(field, value):
    with pytest.raises(SettingsValidationError, match=field):
        validate_settings(settings_factory(**{field: value}))


@pytest.mark.unit
@pytest.mark.parametrize("every", [1, 7])
def test_settings_raise_when_long_break_every_out_of_range(every):
    with pytest.raises(SettingsValidationError, match="long_break_every"):
        validate_settings(settings_factory(long_break_every=every))


@pytest.mark.unit
def test_day_plan_is_valid_when_slots_unique_and_known():
    t1, t2 = task_factory(), task_factory()
    plan = _plan(slot_factory(sector=1, task_id=t1.id), slot_factory(sector=2, task_id=t2.id))

    validate_day_plan(plan, {t1.id: t1, t2.id: t2})


@pytest.mark.unit
def test_day_plan_raises_when_empty():
    with pytest.raises(DayPlanValidationError, match="at least one slot"):
        validate_day_plan(_plan(), {})


@pytest.mark.unit
def test_day_plan_raises_when_duplicate_sectors():
    t1, t2 = task_factory(), task_factory()
    plan = _plan(slot_factory(sector=1, task_id=t1.id), slot_factory(sector=1, task_id=t2.id))

    with pytest.raises(DayPlanValidationError, match="duplicate sectors"):
        validate_day_plan(plan, {t1.id: t1, t2.id: t2})


@pytest.mark.unit
@pytest.mark.parametrize("sector", [0, 13])
def test_day_plan_raises_when_sector_out_of_range(sector):
    task = task_factory()
    plan = _plan(slot_factory(sector=sector, task_id=task.id))

    with pytest.raises(DayPlanValidationError, match="sector must be"):
        validate_day_plan(plan, {task.id: task})


@pytest.mark.unit
def test_day_plan_raises_when_slot_refs_unknown_task():
    plan = _plan(slot_factory(sector=1, task_id="ghost"))

    with pytest.raises(DayPlanValidationError, match="unknown task"):
        validate_day_plan(plan, {})


@pytest.mark.unit
def test_day_plan_raises_when_task_exceeds_estimate_chunk_cap():
    task = task_factory(estimate_blocks=2)
    plan = _plan(*[slot_factory(sector=i, task_id=task.id) for i in (1, 2, 3)])

    with pytest.raises(DayPlanValidationError, match="uses 3 slots, max 2"):
        validate_day_plan(plan, {task.id: task})


@pytest.mark.unit
def test_day_plan_allows_chunk_within_estimate():
    task = task_factory(estimate_blocks=3)
    plan = _plan(*[slot_factory(sector=i, task_id=task.id) for i in (1, 2, 3)])

    validate_day_plan(plan, {task.id: task})


VALID_PATHS = [
    (TaskStatus.BACKLOG, TaskStatus.PLANNED),
    (TaskStatus.PLANNED, TaskStatus.DOING),
    (TaskStatus.DOING, TaskStatus.DONE),
    (TaskStatus.DONE, TaskStatus.DOING),
    (TaskStatus.DOING, TaskStatus.ARCHIVED),
    (TaskStatus.ARCHIVED, TaskStatus.BACKLOG),
    (TaskStatus.PLANNED, TaskStatus.BACKLOG),
]

INVALID_PATHS = [
    (TaskStatus.BACKLOG, TaskStatus.DOING),
    (TaskStatus.BACKLOG, TaskStatus.DONE),
    (TaskStatus.PLANNED, TaskStatus.DONE),
    (TaskStatus.DONE, TaskStatus.ARCHIVED),
    (TaskStatus.ARCHIVED, TaskStatus.PLANNED),
    (TaskStatus.DONE, TaskStatus.BACKLOG),
]

_TRANSITION_IDS = [f"{a.value}>{b.value}" for a, b in VALID_PATHS + INVALID_PATHS]


@pytest.mark.unit
@pytest.mark.parametrize(("old", "new"), VALID_PATHS, ids=_TRANSITION_IDS[: len(VALID_PATHS)])
def test_status_transition_allowed_when_in_machine(old, new):
    validate_status_transition(old, new)


@pytest.mark.unit
@pytest.mark.parametrize(("old", "new"), INVALID_PATHS, ids=_TRANSITION_IDS[len(VALID_PATHS) :])
def test_status_transition_raises_when_outside_machine(old, new):
    with pytest.raises(StatusTransitionError, match="illegal status transition"):
        validate_status_transition(old, new)


@pytest.mark.unit
def test_planning_ready_is_soft_when_science_not_required():
    validate_planning_ready(task_factory(), require_science_fields=False)


@pytest.mark.unit
def test_planning_ready_raises_when_science_required_and_no_when_then():
    with pytest.raises(ScienceFieldRequiredError, match="needs when_then"):
        validate_planning_ready(task_factory(when_then=None), require_science_fields=True)


@pytest.mark.unit
@pytest.mark.parametrize("when_then", ["", "   "], ids=["empty", "whitespace"])
def test_planning_ready_raises_when_when_then_blank_and_required(when_then):
    with pytest.raises(ScienceFieldRequiredError):
        validate_planning_ready(task_factory(when_then=when_then), require_science_fields=True)
