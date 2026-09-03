"""Unit tests for spaced repetition and planning-fallacy buffer (spec 01 §6)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from pomotivato.core.errors import TaskValidationError
from pomotivato.core.models import RepetitionState, Task
from pomotivato.core.science import (
    LAST_INTERVAL_IDX,
    SPACED_INTERVALS_DAYS,
    advance_repetition,
    recommended_start,
)
from pomotivato.core.validation import validate_deadline_realism
from tests.factories.core_models import task_factory

MON = date(2026, 9, 7)


@pytest.mark.unit
def test_advance_due_review_moves_to_next_interval():  # S1: idx1(3d) due -> idx2(7d)
    state = RepetitionState(task_id="t1", interval_idx=1, next_due=MON)

    advanced = advance_repetition(state, MON)

    assert advanced.interval_idx == 2
    assert advanced.next_due == MON + timedelta(days=7)
    assert advanced.task_id == "t1"


@pytest.mark.unit
def test_advance_is_noop_before_due():  # S2
    state = RepetitionState(task_id="t1", interval_idx=0, next_due=MON + timedelta(days=1))

    assert advance_repetition(state, MON) is state


@pytest.mark.unit
def test_advance_matures_by_one_step_per_call():  # 1 -> 3 -> 7
    state = RepetitionState(task_id="t1", interval_idx=0, next_due=MON)

    first = advance_repetition(state, MON)
    second = advance_repetition(first, first.next_due)

    assert first.interval_idx == 1 and first.next_due == MON + timedelta(days=3)
    assert second.interval_idx == 2 and second.next_due == MON + timedelta(days=3) + timedelta(
        days=7
    )


@pytest.mark.unit
def test_last_interval_sticks_at_thirty_days():  # S3
    state = RepetitionState(task_id="t1", interval_idx=LAST_INTERVAL_IDX, next_due=MON)

    advanced = advance_repetition(state, MON)

    assert advanced.interval_idx == LAST_INTERVAL_IDX
    assert advanced.next_due == MON + timedelta(days=30)


@pytest.mark.unit
@pytest.mark.parametrize(
    "idx",
    range(1, len(SPACED_INTERVALS_DAYS)),
    ids=[str(i) for i in range(1, len(SPACED_INTERVALS_DAYS))],
)
def test_each_interval_schedules_its_gap(idx):
    # advancing from idx-1 lands on idx, whose gap is SPACED_INTERVALS_DAYS[idx]
    state = RepetitionState(task_id="t", interval_idx=idx - 1, next_due=MON)

    advanced = advance_repetition(state, MON)

    assert advanced.interval_idx == idx
    assert advanced.next_due == MON + timedelta(days=SPACED_INTERVALS_DAYS[idx])


@pytest.mark.unit
def test_late_review_anchors_next_due_on_review_day_not_schedule():
    # reviewed three days late: the 7-day gap counts from today, not the old due
    state = RepetitionState(task_id="t1", interval_idx=0, next_due=MON)
    late = MON + timedelta(days=3)

    advanced = advance_repetition(state, late)

    assert advanced.next_due == late + timedelta(days=3)


@pytest.mark.unit
def test_recommended_start_pads_estimate_by_buffer_ratio():  # P1: 4 blocks, ratio .25
    deadline = MON + timedelta(days=10)

    start = recommended_start(deadline, 4)

    assert start == deadline - timedelta(days=5)  # ceil(4*1.25)=5 >= 4+1


@pytest.mark.unit
def test_recommended_start_honours_one_day_floor():  # P2: 1 block -> 2 days back
    start = recommended_start(MON, 1, buffer_ratio=0.0)

    assert start == MON - timedelta(days=2)  # floor blocks+1 even with no buffer


@pytest.mark.unit
def test_recommended_start_large_pad_wins_over_floor():
    deadline = MON + timedelta(days=30)

    start = recommended_start(deadline, 10, buffer_ratio=0.5)

    assert start == deadline - timedelta(days=15)  # ceil(15)=15 > 11


@pytest.mark.unit
@pytest.mark.parametrize("blocks", [0, -2])
def test_recommended_start_rejects_non_positive_estimate(blocks):
    with pytest.raises(Exception, match="estimate_blocks"):
        recommended_start(MON, blocks)


@pytest.mark.unit
def test_recommended_start_rejects_negative_buffer():
    with pytest.raises(Exception, match="buffer_ratio"):
        recommended_start(MON, 3, buffer_ratio=-0.1)


# ------------------------------------------------------------------- V6 wiring


def _task(created: date, deadline: date, blocks: int) -> Task:
    return task_factory(
        estimate_blocks=blocks,
        deadline=deadline,
        created_at=datetime(created.year, created.month, created.day, tzinfo=UTC),
    )


@pytest.mark.unit
def test_deadline_task_passes_when_runway_fits():  # P3 mirror: 10d, 4 blocks, start -5d
    validate_deadline_realism(_task(MON, MON + timedelta(days=10), 4))


@pytest.mark.unit
def test_deadline_task_raises_when_plan_no_longer_fits():
    # 4 blocks need 5 days of runway, but only 3 remain at creation
    task = _task(MON, MON + timedelta(days=3), 4)

    with pytest.raises(TaskValidationError, match="is unrealistic"):
        validate_deadline_realism(task)


@pytest.mark.unit
def test_task_without_deadline_always_passes_v6():
    validate_deadline_realism(task_factory(deadline=None))
