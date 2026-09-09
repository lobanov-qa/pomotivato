"""frog_candidate unit tests (spec 05 §3.9): pure suggestion, never reorders."""

from __future__ import annotations

from datetime import timedelta

import pytest

from pomotivato.core.models import TaskStatus
from pomotivato.core.science import FROG_MIN_BLOCKS, frog_candidate
from tests.factories.core_models import DEFAULT_MOMENT, task_factory


@pytest.mark.unit
def test_frog_none_when_all_tasks_small():
    tasks = (task_factory(estimate_blocks=1), task_factory(estimate_blocks=2))
    assert frog_candidate(tasks) is None


@pytest.mark.unit
def test_frog_none_when_empty_or_all_done():
    assert frog_candidate(()) is None
    done = (task_factory(estimate_blocks=5, status=TaskStatus.DONE),)
    assert frog_candidate(done) is None


@pytest.mark.unit
def test_frog_skips_no_timer_errands():  # DF13: an errand is not a frog
    errand = task_factory(estimate_blocks=9, no_timer=True)
    timer_task = task_factory(estimate_blocks=3)
    assert frog_candidate((errand, timer_task)) is timer_task
    assert frog_candidate((errand,)) is None


@pytest.mark.unit
def test_frog_picks_biggest_estimate():
    small = task_factory(estimate_blocks=FROG_MIN_BLOCKS)
    big = task_factory(estimate_blocks=7)
    assert frog_candidate((small, big)) is big


@pytest.mark.unit
def test_frog_breaks_ties_toward_quadrant_two():
    # equal size: important-and-not-urgent wins over important-and-urgent
    urgent = task_factory(estimate_blocks=5, important=True, urgent=True)
    deep = task_factory(estimate_blocks=5, important=True, urgent=False)
    assert frog_candidate((urgent, deep)) is deep


@pytest.mark.unit
def test_frog_breaks_further_ties_toward_oldest():
    fresh = task_factory(estimate_blocks=5, important=True, urgent=False)
    old = task_factory(
        estimate_blocks=5,
        important=True,
        urgent=False,
        created_at=DEFAULT_MOMENT - timedelta(days=3),
    )
    assert frog_candidate((fresh, old)) is old


@pytest.mark.unit
def test_frog_ignores_archived_even_when_big():
    archived = task_factory(estimate_blocks=9, status=TaskStatus.ARCHIVED)
    open_task = task_factory(estimate_blocks=FROG_MIN_BLOCKS)
    assert frog_candidate((archived, open_task)) is open_task
