"""Unit tests for recurrence expansion and day reordering (spec 01 §5/§5.1)."""

from __future__ import annotations

from datetime import date

import pytest

from pomotivato.core.errors import DayPlanValidationError, RecurrenceValidationError
from pomotivato.core.models import Daily, DayPlan, Once, Slot, WeeklyCount, WeeklyDays
from pomotivato.core.schedule import expand_recurrence, move_slot

AUG_31 = date(2026, 8, 31)  # Monday
SEP_6 = date(2026, 9, 6)  # Sunday
SEP_2 = date(2026, 9, 2)  # Wednesday


def plan(*task_ids: str) -> DayPlan:
    slots = tuple(Slot(sector=i + 1, task_id=t) for i, t in enumerate(task_ids))
    return DayPlan(id="p", date=SEP_2, slots=slots)


def order_of(result: DayPlan) -> tuple[str, ...]:
    """Task ids in sector order (what the dial shows as 1st, 2nd, ...)."""
    return tuple(slot.task_id for slot in sorted(result.slots, key=lambda s: s.sector))


# ------------------------------------------------------------- expand_recurrence


@pytest.mark.unit
def test_once_expands_to_nothing_when_range_covers_week():  # R-Once
    assert expand_recurrence(Once(), AUG_31, SEP_6) == ()


@pytest.mark.unit
def test_daily_expands_to_every_day_in_inclusive_range():  # R1
    days = expand_recurrence(Daily(), AUG_31, SEP_6)

    assert len(days) == 7
    assert days[0] == AUG_31 and days[-1] == SEP_6
    assert days == tuple(sorted(days))


@pytest.mark.unit
def test_weekly_days_picks_only_masked_weekdays():  # R2 (Mon+Fri)
    days = expand_recurrence(WeeklyDays(frozenset({0, 4})), AUG_31, date(2026, 9, 13))

    assert days == (date(2026, 8, 31), date(2026, 9, 4), date(2026, 9, 7), date(2026, 9, 11))


@pytest.mark.unit
def test_weekly_count_picks_n_earliest_days_per_iso_week():  # R3
    days = expand_recurrence(WeeklyCount(n=3, start=SEP_2), AUG_31, date(2026, 9, 13))

    assert [d.isoformat() for d in days] == [
        "2026-09-02",
        "2026-09-03",
        "2026-09-04",  # week 36: Wed..Fri, 3 days
        "2026-09-07",
        "2026-09-08",
        "2026-09-09",  # week 37: Mon..Wed
    ]
    assert len(set(days)) == len(days)


@pytest.mark.unit
def test_weekly_count_never_before_start():  # R5
    days = expand_recurrence(WeeklyCount(n=3, start=SEP_2), AUG_31, SEP_6)

    assert all(d >= SEP_2 for d in days)
    assert days == (SEP_2, date(2026, 9, 3), date(2026, 9, 4))


@pytest.mark.unit
def test_expansion_is_empty_when_range_inverted():  # R4
    assert expand_recurrence(Daily(), SEP_6, AUG_31) == ()
    assert expand_recurrence(WeeklyDays(frozenset({0})), SEP_6, AUG_31) == ()
    assert expand_recurrence(WeeklyCount(n=2, start=AUG_31), SEP_6, AUG_31) == ()


@pytest.mark.unit
def test_single_day_range_returns_that_day_when_matching():
    monday = date(2026, 8, 31)

    assert expand_recurrence(WeeklyDays(frozenset({0})), monday, monday) == (monday,)
    assert expand_recurrence(WeeklyDays(frozenset({4})), monday, monday) == ()


@pytest.mark.unit
def test_expand_refuses_invalid_recurrence_parameters():
    with pytest.raises(RecurrenceValidationError, match="weekdays"):
        expand_recurrence(WeeklyDays(frozenset()), AUG_31, SEP_6)
    with pytest.raises(RecurrenceValidationError, match="n must be 1..6"):
        expand_recurrence(WeeklyCount(n=7, start=AUG_31), AUG_31, SEP_6)


# -------------------------------------------------------------------- move_slot


@pytest.mark.unit
def test_move_slot_reinserts_task_at_position():  # M1 [A,B,C] 3->1
    result = move_slot(plan("A", "B", "C"), 3, 1)

    assert order_of(result) == ("C", "A", "B")


@pytest.mark.unit
def test_move_slot_renumbers_sectors_densely():
    gappy = DayPlan(
        id="p", date=SEP_2, slots=(Slot(sector=3, task_id="A"), Slot(sector=9, task_id="B"))
    )

    result = move_slot(gappy, 2, 1)

    assert [slot.sector for slot in result.slots] == [1, 2]
    assert order_of(result) == ("B", "A")


@pytest.mark.unit
def test_move_slot_sends_chunk_of_same_task_as_one_block():  # M2 [A,A,B] B->1
    result = move_slot(plan("A", "A", "B"), 3, 1)

    assert order_of(result) == ("B", "A", "A")


@pytest.mark.unit
def test_move_slot_keeps_chunk_internal_order_when_moving_backward():  # M2 reverse
    result = move_slot(plan("B", "A", "A"), 2, 3)

    assert order_of(result) == ("B", "A", "A")  # A-block lands last, unchanged order
    result2 = move_slot(plan("A", "B", "A"), 1, 3)
    assert order_of(result2) == ("B", "A", "A")


@pytest.mark.unit
def test_move_slot_to_same_position_is_idempotent_noop():  # M3
    source = plan("A", "B", "C")

    assert move_slot(source, 2, 2) is source


@pytest.mark.unit
def test_move_slot_rejects_positions_out_of_range():  # M3
    source = plan("A", "B")

    for pos_from, pos_to in [(0, 1), (3, 1), (1, 0), (1, 3), (-1, 2)]:
        with pytest.raises(DayPlanValidationError, match="positions must be 1..2"):
            move_slot(source, pos_from, pos_to)
    assert order_of(source) == ("A", "B")  # untouched


@pytest.mark.unit
def test_move_slot_returns_new_object_leaving_source_frozen():
    source = plan("A", "B", "C")

    result = move_slot(source, 1, 3)

    assert order_of(source) == ("A", "B", "C")
    assert order_of(result) == ("B", "C", "A")
    assert result.id == source.id and result.date == source.date
