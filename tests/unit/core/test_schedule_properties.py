"""Property tests for recurrence expansion and slot ordering (spec 01 §8 P4/P9)."""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from pomotivato.core.models import Daily, DayPlan, Once, Slot, WeeklyCount, WeeklyDays
from pomotivato.core.schedule import expand_recurrence, move_slot

pytestmark = pytest.mark.property

DAYS_AHEAD = st.integers(min_value=-400, max_value=400)
WEEKDAY_MASK = st.frozensets(st.integers(min_value=0, max_value=6), min_size=1)
RECURRENCE = st.one_of(
    st.just(Once()),
    st.just(Daily()),
    WEEKDAY_MASK.map(WeeklyDays),
    st.builds(
        WeeklyCount,
        n=st.integers(min_value=1, max_value=6),
        start=st.dates(min_value=date(2024, 1, 1), max_value=date(2026, 12, 31)),
    ),
)


@st.composite
def day_range(draw):
    anchor = draw(st.dates(min_value=date(2024, 1, 1), max_value=date(2026, 12, 31)))
    length = draw(st.integers(min_value=0, max_value=60))
    return anchor, anchor + timedelta(days=length)


def plan_of(task_ids: list[str]) -> DayPlan:
    return DayPlan(
        id="p",
        date=date(2026, 9, 3),
        slots=tuple(Slot(sector=i + 1, task_id=t) for i, t in enumerate(task_ids)),
    )


@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(rec=RECURRENCE, rng=day_range())
def test_expansion_is_sorted_unique_and_within_bounds(rec, rng):  # P4
    date_from, date_to = rng

    days = expand_recurrence(rec, date_from, date_to)

    assert list(days) == sorted(days)
    assert len(set(days)) == len(days)
    assert all(date_from <= d <= date_to for d in days)
    if date_to < date_from:
        assert days == ()


@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(mask=WEEKDAY_MASK, rng=day_range())
def test_weekly_days_matches_mask_and_daily_length_matches_range(mask, rng):  # P4
    date_from, date_to = rng

    days = expand_recurrence(WeeklyDays(mask), date_from, date_to)

    expected = tuple(
        d for d in expand_recurrence(Daily(), date_from, date_to) if d.weekday() in mask
    )
    assert days == expected


@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    n=st.integers(min_value=1, max_value=6),
    rng=day_range(),
    start=st.dates(min_value=date(2024, 1, 1), max_value=date(2026, 12, 31)),
)
def test_weekly_count_respects_n_per_iso_week_and_start(n, rng, start):  # P4
    date_from, date_to = rng

    days = expand_recurrence(WeeklyCount(n=n, start=start), date_from, date_to)

    assert all(d >= start for d in days)
    per_week = Counter(d.isocalendar()[:2] for d in days)
    assert all(count <= n for count in per_week.values())


@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    task_ids=st.lists(st.sampled_from(["A", "B", "C", "D", "E"]), min_size=1, max_size=8),
    pos_from=st.integers(min_value=1, max_value=8),
    pos_to=st.integers(min_value=1, max_value=8),
)
def test_move_slot_is_a_permutation_with_dense_sectors(task_ids, pos_from, pos_to):  # P9
    assume(pos_from <= len(task_ids) and pos_to <= len(task_ids))
    source = plan_of(task_ids)

    result = move_slot(source, pos_from, pos_to)

    assert Counter(slot.task_id for slot in result.slots) == Counter(task_ids)
    assert sorted(slot.sector for slot in result.slots) == list(range(1, len(task_ids) + 1))
    # moved task occupies the same set of tasks as before, counts preserved
    assert Counter(slot.task_id for slot in result.slots) == Counter(
        slot.task_id for slot in source.slots
    )


@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    task_ids=st.lists(st.sampled_from(["A", "B", "C", "D"]), min_size=1, max_size=8),
    pos_from=st.integers(min_value=1, max_value=8),
    pos_to=st.integers(min_value=1, max_value=8),
)
def test_moved_task_lands_as_one_contiguous_block(task_ids, pos_from, pos_to):  # §5.1 M2
    assume(pos_from <= len(task_ids) and pos_to <= len(task_ids))
    # the no-op path returns the source as-is (spec M3, unit-covered) and
    # must not "fix" a pre-existing non-contiguous layout — exclude it here
    assume(pos_from != pos_to)
    plan = plan_of(task_ids)
    moved = sorted(plan.slots, key=lambda s: s.sector)[pos_from - 1].task_id

    result = move_slot(plan, pos_from, pos_to)

    sector_order = [slot.task_id for slot in sorted(result.slots, key=lambda s: s.sector)]
    positions = [i for i, t in enumerate(sector_order) if t == moved]
    assert positions == list(range(positions[0], positions[0] + len(positions)))
    assert Counter(sector_order) == Counter(task_ids)
