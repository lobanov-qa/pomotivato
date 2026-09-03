"""Property tests for spaced repetition and planning buffer (spec 01 §8 P5/P6)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from pomotivato.core.models import RepetitionState
from pomotivato.core.science import (
    LAST_INTERVAL_IDX,
    SPACED_INTERVALS_DAYS,
    advance_repetition,
    recommended_start,
)

pytestmark = pytest.mark.property

DATES = st.dates(min_value=date(2024, 1, 1), max_value=date(2027, 12, 31))
INDICES = st.integers(min_value=0, max_value=LAST_INTERVAL_IDX)


@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    idx=INDICES,
    next_due=DATES,
    today=DATES,
)
def test_repetition_advances_monotonically_and_stays_in_intervals(idx, next_due, today):  # P5
    state = RepetitionState(task_id="t", interval_idx=idx, next_due=next_due)

    advanced = advance_repetition(state, today)

    if today < next_due:
        assert advanced is state
    else:
        assert idx <= advanced.interval_idx <= LAST_INTERVAL_IDX
        # reviewed at/after due with a >=1 day gap: next review strictly later
        assert advanced.next_due > next_due
        assert advanced.next_due == today + timedelta(
            days=SPACED_INTERVALS_DAYS[advanced.interval_idx]
        )
        assert advanced.task_id == state.task_id


@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    idx=INDICES,
    next_due=DATES,
    today=DATES,
    extra=st.integers(min_value=0, max_value=5),
)
def test_repeated_advances_never_regress(idx, next_due, today, extra):
    state = RepetitionState(task_id="t", interval_idx=idx, next_due=next_due)

    result = state
    for _ in range(extra):
        # review on/after the due date: each iteration must actually advance
        result = advance_repetition(result, max(today, result.next_due))

    assert result.interval_idx >= idx
    if extra > 0:
        assert result.next_due > state.next_due


@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    blocks=st.integers(min_value=1, max_value=50),
    ratio=st.floats(min_value=0.0, max_value=1.5, allow_nan=False),
    deadline=DATES,
)
def test_recommended_start_is_always_earlier_than_deadline(blocks, ratio, deadline):  # P6
    assume(deadline > date(2024, 1, 10))

    start = recommended_start(deadline, blocks, buffer_ratio=ratio)

    assert start < deadline
    assert (deadline - start).days >= blocks + 1


@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    blocks=st.integers(min_value=1, max_value=50),
    deadline=DATES,
)
def test_larger_buffer_never_moves_start_closer_to_deadline(blocks, deadline):  # P6
    assume(deadline > date(2024, 2, 1))

    plain = recommended_start(deadline, blocks, buffer_ratio=0.0)
    padded = recommended_start(deadline, blocks, buffer_ratio=0.5)

    assert padded <= plain
