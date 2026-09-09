"""Unit tests for the pure planner + hints projections (spec 05 §3.2/§3.6)."""

from __future__ import annotations

from datetime import date

import pytest

from pomotivato.core.models import (
    Daily,
    DayPlan,
    Once,
    SessionSettings,
    Slot,
    Task,
    TaskStatus,
    WeeklyDays,
)
from pomotivato.services.blocks import WorkBlock
from pomotivato.services.hints import Hint, compute_hints
from pomotivato.services.planner import activate_recurring, add_task_to_plan
from tests.factories.core_models import day_plan_factory, task_factory

TUESDAY = date(2026, 9, 8)


def empty_plan() -> DayPlan:
    return day_plan_factory(slots=())


def recurring(**overrides: object) -> Task:
    args: dict[str, object] = {
        "status": TaskStatus.DOING,
        "recurrence": Daily(),
        "estimate_blocks": 1,
    }
    args.update(overrides)
    return task_factory(**args)


# ---------------------------------------------------------------- add primitive


@pytest.mark.unit
def test_add_appends_task_chunk_to_free_sectors():
    task = recurring(estimate_blocks=2)

    outcome = add_task_to_plan(empty_plan(), task)

    assert [(s.sector, s.task_id) for s in outcome.plan.slots] == [
        (1, task.id),
        (2, task.id),
    ]
    assert outcome.added == (task.id,) and outcome.skipped == ()


@pytest.mark.unit
def test_add_is_idempotent_when_task_fully_scheduled():
    task = recurring(estimate_blocks=1)
    once = add_task_to_plan(empty_plan(), task)

    twice = add_task_to_plan(once.plan, task)

    assert twice.plan.slots == once.plan.slots
    assert twice.added == () and twice.skipped == ()


@pytest.mark.unit
def test_add_reports_skip_when_day_is_full():
    busy = empty_plan()
    for _ in range(12):  # twelve ONE-slot tasks, not one repeated: each add
        busy = add_task_to_plan(busy, recurring()).plan  # fills exactly one
    intruder = recurring(estimate_blocks=3)

    outcome = add_task_to_plan(busy, intruder)

    assert outcome.plan.slots == busy.slots
    assert outcome.added == () and outcome.skipped == (intruder.id,)


@pytest.mark.unit
def test_add_grows_partial_chunk_up_to_estimate():
    task = recurring(estimate_blocks=3)
    # a chunk cut short by capacity: two of three slots, sector 3 now free
    partial = day_plan_factory(
        slots=(Slot(1, task.id), Slot(2, task.id)),
    )

    grown = add_task_to_plan(partial, task)

    assert [s.sector for s in grown.plan.slots] == [1, 2, 3]


# ---------------------------------------------------------------- activation


@pytest.mark.unit
def test_activate_materializes_daily_task_once():  # GWT-A1
    task = recurring()

    outcome = activate_recurring(empty_plan(), (task,), TUESDAY)

    assert [(s.sector, s.task_id) for s in outcome.plan.slots] == [(1, task.id)]
    assert outcome.added == (task.id,)


@pytest.mark.unit
def test_activate_is_idempotent():  # GWT-A2
    task = recurring()
    first = activate_recurring(empty_plan(), (task,), TUESDAY)

    second = activate_recurring(first.plan, (task,), TUESDAY)

    assert second.plan.slots == first.plan.slots
    assert second.added == () and second.skipped == ()


@pytest.mark.unit
def test_activate_skips_when_no_capacity_and_keeps_plan():  # GWT-A3
    intruder = recurring()
    busy = empty_plan()
    for _ in range(12):
        busy = add_task_to_plan(busy, recurring()).plan

    outcome = activate_recurring(busy, (intruder,), TUESDAY)

    assert outcome.plan.slots == busy.slots
    assert outcome.skipped == (intruder.id,)


@pytest.mark.unit
def test_activate_ignores_non_matching_weekdays():  # GWT-A4
    tuesday_only = recurring(recurrence=WeeklyDays(frozenset({1})))  # Tue=1
    wednesday = date(2026, 9, 9)

    outcome = activate_recurring(empty_plan(), (tuesday_only,), wednesday)

    assert outcome.plan.slots == () and outcome.added == ()


@pytest.mark.unit
def test_activate_skips_once_habit_and_done():  # GWT-A5 + status guard
    once = recurring(recurrence=Once())
    done = recurring(status=TaskStatus.DONE)
    archived = recurring(status=TaskStatus.ARCHIVED)

    outcome = activate_recurring(empty_plan(), (once, done, archived), TUESDAY)

    assert outcome.plan.slots == ()


@pytest.mark.unit
def test_activate_skips_no_timer_errand_even_when_recurring():
    """DF13: an errand is never day work, not even a recurring one."""
    errand = recurring(no_timer=True)

    outcome = activate_recurring(empty_plan(), (errand,), TUESDAY)

    assert outcome.plan.slots == ()


@pytest.mark.unit
def test_activate_order_is_deterministic_by_task_id():
    later = recurring(id="task-z", recurrence=Daily())
    earlier = recurring(id="task-a", recurrence=Daily())

    outcome = activate_recurring(empty_plan(), (later, earlier), TUESDAY)

    assert [s.task_id for s in outcome.plan.slots] == ["task-a", "task-z"]


# ---------------------------------------------------------------- hints rules


def block(task_id: str, minutes: int = 25, seg: int = 0) -> WorkBlock:
    return WorkBlock(segment_id=f"seg-{seg}", task_id=task_id, day=TUESDAY, minutes=minutes)


SETTINGS = SessionSettings()


def kinds(hints: tuple[Hint, ...]) -> list[str]:
    return [h.kind for h in hints]


@pytest.mark.unit
def test_break_always_earns_the_diffuse_hint():
    hints = compute_hints((), (), {}, frozenset(), in_break=True, settings=SETTINGS)
    assert hints[0].kind == "diffuse"
    assert compute_hints((), (), {}, frozenset(), in_break=False, settings=SETTINGS) == ()


@pytest.mark.unit
def test_interleaving_fires_after_three_blocks_of_one_parent():
    a, b = task_factory(parent_id="goal"), task_factory(parent_id="goal")
    blocks = (block(a.id, seg=1), block(b.id, seg=2), block(a.id, seg=3))
    tasks = {a.id: a, b.id: b}

    hints = compute_hints(blocks, (), tasks, frozenset(), in_break=False, settings=SETTINGS)

    assert "interleaving" in kinds(hints)
    # a two-block streak does not:
    short = compute_hints(blocks[:2], (), tasks, frozenset(), in_break=False, settings=SETTINGS)
    assert "interleaving" not in kinds(short)


@pytest.mark.unit
def test_overlearning_uses_estimate_times_work_min_and_counts_open_burn():
    task = task_factory(estimate_blocks=2)  # budget 2*25=50 min
    tasks = {task.id: task}

    fired = compute_hints(
        (block(task.id, minutes=26, seg=1), block(task.id, minutes=26, seg=2)),
        (),
        tasks,
        frozenset(),
        in_break=False,
        settings=SETTINGS,
    )
    assert "overlearning" in kinds(fired)

    mid = compute_hints(
        (block(task.id, minutes=30, seg=1),),
        (),
        tasks,
        frozenset(),
        in_break=False,
        settings=SETTINGS,
        open_task_id=task.id,
        open_minutes_spent=25,
    )
    assert "overlearning" in kinds(mid)  # 30+25 > 50 — hears it while burning
    under = compute_hints(
        (block(task.id, minutes=30, seg=1),),
        (),
        tasks,
        frozenset(),
        in_break=False,
        settings=SETTINGS,
    )
    assert "overlearning" not in kinds(under)  # 30 < 50, still fine


@pytest.mark.unit
def test_einstellung_needs_two_interrupts_of_one_task():
    task = task_factory()
    once = compute_hints(
        (), (task.id,), {task.id: task}, frozenset(), in_break=False, settings=SETTINGS
    )
    twice = compute_hints(
        (),
        (task.id, task.id),
        {task.id: task},
        frozenset(),
        in_break=False,
        settings=SETTINGS,
    )
    assert "einstellung" not in kinds(once)
    assert "einstellung" in kinds(twice)


@pytest.mark.unit
def test_frog_hint_only_in_break_when_planned_and_untouched():
    frog = task_factory(estimate_blocks=4, status=TaskStatus.DOING, important=True)
    tasks = {frog.id: frog}

    on_break = compute_hints((), (), tasks, frozenset({frog.id}), in_break=True, settings=SETTINGS)
    assert "frog" in kinds(on_break)

    done_already = compute_hints(
        (block(frog.id, seg=1),),
        (),
        tasks,
        frozenset({frog.id}),
        in_break=True,
        settings=SETTINGS,
    )
    assert "frog" not in kinds(done_already)

    while_working = compute_hints(
        (), (), tasks, frozenset({frog.id}), in_break=False, settings=SETTINGS
    )
    assert "frog" not in kinds(while_working)
