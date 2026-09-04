"""Service floor for day plans: upsert identity, core bounds, slot moves."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Any

import pytest

from pomotivato.core.errors import DayPlanValidationError
from pomotivato.core.models import DayPlan, Slot
from pomotivato.infra.errors import NotFoundError
from tests.factories.core_models import DEFAULT_MOMENT, day_plan_factory, task_factory


def _plan_with(*task_ids: str, day: date | None = None) -> DayPlan:
    slots = tuple(Slot(sector=idx + 1, task_id=tid) for idx, tid in enumerate(task_ids))
    return day_plan_factory(slots=slots, **({"date": day} if day else {}))


@pytest.mark.api
def test_upsert_then_get_roundtrips_when_plan_saved(database, call):
    async def scenario() -> Any:
        async with call() as svc:
            first = await svc.task.create(task_factory())
            second = await svc.task.create(task_factory())
            plan = _plan_with(first.id, second.id)
            await svc.day_plan.upsert(plan)
        async with call() as svc:
            return plan, await svc.day_plan.get(DEFAULT_MOMENT.date())

    saved, loaded = asyncio.run(scenario())

    assert loaded.date == saved.date
    assert [(s.sector, s.task_id) for s in loaded.slots] == [
        (s.sector, s.task_id) for s in saved.slots
    ]


@pytest.mark.api
def test_upsert_twice_same_date_keeps_one_row_when_plan_edited(database, call):
    async def scenario() -> Any:
        async with call() as svc:
            a = await svc.task.create(task_factory())
            b = await svc.task.create(task_factory())
        day = DEFAULT_MOMENT.date()
        async with call() as svc:
            await svc.day_plan.upsert(_plan_with(a.id, day=day))
        async with call() as svc:
            await svc.day_plan.upsert(_plan_with(a.id, b.id, day=day))
        async with call() as svc:
            return await svc.day_plan.get(day)

    final = asyncio.run(scenario())

    assert len(final.slots) == 2


@pytest.mark.api
def test_upsert_rejects_slot_for_unknown_task_when_reference_dangles(database, call):
    async def scenario() -> Any:
        async with call() as svc:
            await svc.day_plan.upsert(_plan_with("ghost-task"))

    with pytest.raises(DayPlanValidationError):
        asyncio.run(scenario())


@pytest.mark.api
def test_upsert_rejects_more_slots_than_estimate_when_v10_breaks(database, call):
    async def scenario() -> Any:
        async with call() as svc:
            small = await svc.task.create(task_factory(estimate_blocks=1))
        async with call() as svc:
            await svc.day_plan.upsert(_plan_with(small.id, small.id))

    with pytest.raises(DayPlanValidationError):
        asyncio.run(scenario())


@pytest.mark.api
def test_move_reorders_and_renumbers_when_slot_dragged(database, call):
    async def scenario() -> Any:
        async with call() as svc:
            a = await svc.task.create(task_factory())
            b = await svc.task.create(task_factory())
            c = await svc.task.create(task_factory())
        day = DEFAULT_MOMENT.date()
        async with call() as svc:
            await svc.day_plan.upsert(_plan_with(a.id, b.id, c.id, day=day))
        async with call() as svc:
            moved = await svc.day_plan.move(day, pos_from=3, pos_to=1)
        return a.id, b.id, c.id, moved

    first_id, second_id, third_id, moved = asyncio.run(scenario())

    assert [s.task_id for s in moved.slots] == [third_id, first_id, second_id]
    assert [s.sector for s in moved.slots] == [1, 2, 3]


@pytest.mark.api
def test_move_persists_when_transaction_committed(database, call):
    async def scenario() -> Any:
        async with call() as svc:
            a = await svc.task.create(task_factory())
            b = await svc.task.create(task_factory())
        day = DEFAULT_MOMENT.date()
        async with call() as svc:
            await svc.day_plan.upsert(_plan_with(a.id, b.id, day=day))
        async with call() as svc:
            await svc.day_plan.move(day, pos_from=2, pos_to=1)
        async with call() as svc:
            reloaded = await svc.day_plan.get(day)
        return a.id, b.id, reloaded

    first_id, second_id, reloaded = asyncio.run(scenario())

    assert [(s.sector, s.task_id) for s in reloaded.slots] == [
        (1, second_id),
        (2, first_id),
    ]


@pytest.mark.api
def test_move_rejects_out_of_range_when_positions_beyond_plan(database, call):
    async def scenario() -> Any:
        async with call() as svc:
            a = await svc.task.create(task_factory())
        day = DEFAULT_MOMENT.date()
        async with call() as svc:
            await svc.day_plan.upsert(_plan_with(a.id, day=day))
        async with call() as svc:
            await svc.day_plan.move(day, pos_from=1, pos_to=5)

    with pytest.raises(DayPlanValidationError):
        asyncio.run(scenario())


@pytest.mark.api
def test_get_raises_not_found_when_day_has_no_plan(database, call):
    async def scenario() -> Any:
        async with call() as svc:
            await svc.day_plan.get(DEFAULT_MOMENT.date() + timedelta(days=365))

    with pytest.raises(NotFoundError):
        asyncio.run(scenario())
