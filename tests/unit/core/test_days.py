"""Unit tests for the day-close rules (core/days.py, spec 07 §5.1/§5.7).

The pure heart of E4c PR 4: V22 walk, V30 fold, V31/V32 predicates and the
V21 retrospective-mark guard — with the author's two 24.09 bugs as named
regression cases.
"""

from __future__ import annotations

from datetime import date

import pytest

from pomotivato.core.days import (
    all_ticks_worked,
    close_eligible,
    fold_stale_card,
    future_ticks,
    missed_ticks,
    validate_ticks_not_retrospective,
    walk_after_day,
)
from pomotivato.core.errors import RecurrenceValidationError
from pomotivato.core.models import Once, OnDates, Task, TaskStatus
from tests.factories.core_models import task_factory

TODAY = date(2026, 9, 10)
YDAY = date(2026, 9, 9)
TOMORROW = date(2026, 9, 11)


def sprint_task(days: set[date], **overrides: object) -> Task:
    return task_factory(sprint_id="s-1", recurrence=OnDates(frozenset(days)), **overrides)


@pytest.mark.unit
def test_walk_keeps_the_card_in_work_until_the_day_blocks_are_gone() -> None:
    """Author's bug (1) 24.09: a two-sector card must not leave after block 1."""
    card = sprint_task({TODAY, TOMORROW})

    nxt = walk_after_day(
        card, TODAY, day_blocks=2, blocks_done_today=1, worked_days=frozenset({TODAY})
    )

    assert nxt is None  # stays DOING — the second block is still owed


@pytest.mark.unit
def test_walk_returns_to_planned_while_future_ticks_remain() -> None:  # V22(б)
    card = sprint_task({TODAY, TOMORROW})

    nxt = walk_after_day(
        card, TODAY, day_blocks=1, blocks_done_today=1, worked_days=frozenset({TODAY})
    )

    assert nxt is TaskStatus.PLANNED


@pytest.mark.unit
def test_walk_refuses_done_over_a_missed_tick() -> None:
    """V22(в)/V31/S1: yesterday unworked — planned, not done, whatever else."""
    card = sprint_task({YDAY, TODAY})

    nxt = walk_after_day(
        card, TODAY, day_blocks=1, blocks_done_today=1, worked_days=frozenset({TODAY})
    )

    assert nxt is TaskStatus.PLANNED


@pytest.mark.unit
def test_walk_closes_when_every_tick_is_worked() -> None:  # V22(г)/S5
    card = sprint_task({YDAY, TODAY})

    nxt = walk_after_day(
        card, TODAY, day_blocks=1, blocks_done_today=1, worked_days=frozenset({YDAY, TODAY})
    )

    assert nxt is TaskStatus.DONE


@pytest.mark.unit
def test_shelf_card_closes_once_the_day_blocks_are_done() -> None:  # V22(д)/A6
    card = task_factory(sprint_id=None, recurrence=Once())

    assert (
        walk_after_day(card, TODAY, day_blocks=1, blocks_done_today=0, worked_days=frozenset())
        is None
    )
    assert (
        walk_after_day(
            card, TODAY, day_blocks=1, blocks_done_today=1, worked_days=frozenset({TODAY})
        )
        is TaskStatus.DONE
    )


@pytest.mark.unit
def test_shelf_card_with_legacy_ticks_still_closes() -> None:
    """A8: ticks are a sprint-card property — a shelf card never waits on them."""
    card = task_factory(sprint_id=None, recurrence=OnDates(frozenset({TOMORROW})))

    nxt = walk_after_day(card, TODAY, day_blocks=1, blocks_done_today=1, worked_days=frozenset())

    assert nxt is TaskStatus.DONE


@pytest.mark.unit
def test_fold_sends_an_unworked_card_back_to_planned() -> None:  # V30/S6
    card = sprint_task({TODAY})

    assert fold_stale_card(card, TODAY, worked_days=frozenset()) is TaskStatus.PLANNED


@pytest.mark.unit
def test_fold_closes_a_card_that_outran_its_ticks() -> None:
    card = sprint_task({YDAY})

    assert fold_stale_card(card, TODAY, worked_days=frozenset({YDAY})) is TaskStatus.DONE


@pytest.mark.unit
def test_fold_never_fakes_a_finished_card_without_any_work() -> None:  # S15
    card = sprint_task(set())

    assert fold_stale_card(card, TODAY, worked_days=frozenset()) is TaskStatus.PLANNED


@pytest.mark.unit
def test_close_requires_a_finished_block_and_a_spent_calendar() -> None:  # V32
    worked = frozenset({YDAY})

    assert close_eligible(sprint_task({YDAY}), TODAY, worked) is True
    assert close_eligible(sprint_task({YDAY}), TODAY, frozenset()) is False
    assert close_eligible(sprint_task({YDAY, TOMORROW}), TODAY, worked) is False


# ---- helpers' own math -------------------------------------------------------


@pytest.mark.unit
def test_tick_maps_split_future_past_and_worked() -> None:
    card = sprint_task({YDAY, TODAY, TOMORROW})
    worked = frozenset({YDAY})

    assert future_ticks(card, TODAY) == (TOMORROW,)
    assert missed_ticks(card, TODAY, worked) == ()  # TODAY is not past yet
    assert missed_ticks(card, TOMORROW, worked) == (TODAY,)
    assert all_ticks_worked(card, worked) is False


@pytest.mark.unit
def test_non_ticked_recurrences_carry_no_days_at_all() -> None:  # A8
    for rec in (Once(),):
        card = task_factory(sprint_id="s-1", recurrence=rec)
        assert future_ticks(card, TODAY) == ()
        assert missed_ticks(card, TODAY, frozenset()) == ()
        assert all_ticks_worked(card, frozenset()) is True


# ---- V21: marks are not time machines ----------------------------------------


@pytest.mark.unit
def test_new_mark_in_the_past_is_refused_listing_the_days() -> None:
    old = OnDates(frozenset({TOMORROW}))
    new = OnDates(frozenset({TODAY, TOMORROW, YDAY}))

    with pytest.raises(RecurrenceValidationError, match="2026-09-09"):
        validate_ticks_not_retrospective(old, new, TODAY)


@pytest.mark.unit
def test_existing_past_marks_survive_further_edits() -> None:
    """The author's rule: history lives — only a NEW day before today dies."""
    kept = OnDates(frozenset({YDAY, TODAY}))
    validate_ticks_not_retrospective(kept, kept, TODAY)
    grown = OnDates(frozenset({YDAY, TODAY, TOMORROW}))
    validate_ticks_not_retrospective(kept, grown, TODAY)


@pytest.mark.unit
def test_dropping_to_once_is_always_allowed() -> None:
    validate_ticks_not_retrospective(OnDates(frozenset({YDAY})), Once(), TODAY)


@pytest.mark.unit
def test_author_bug_two_work_on_yesterday_cannot_be_marked() -> None:
    """Author's bug (2) 24.09: a sprint-day row used to hand out past marks."""
    card_days = {YDAY, TODAY}  # the row offers a past day of a longer sprint
    sneaky = OnDates(frozenset(card_days))
    before = OnDates(frozenset({TODAY}))

    with pytest.raises(RecurrenceValidationError, match="past"):
        validate_ticks_not_retrospective(before, sneaky, TODAY)
