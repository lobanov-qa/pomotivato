"""DayPlanService: one plan per date, slots validated by core (spec 02 §4)."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from pomotivato.core.models import DayPlan, Slot, Task
from pomotivato.core.schedule import move_slot
from pomotivato.core.validation import validate_day_plan
from pomotivato.infra.errors import NotFoundError
from pomotivato.infra.repository import DayPlanRepository, TaskRepository


class DayPlanService:
    """Upsert, read and reorder the day's slot layout."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._plans = DayPlanRepository(session)
        self._tasks = TaskRepository(session)

    async def _plan_by_date(self, day: date) -> DayPlan:
        plan = await self._plans.get_by_date(day)
        if plan is None:
            msg = f"day plan for {day.isoformat()} not found"
            raise NotFoundError(msg)
        return plan

    async def _tasks_for(self, slots: tuple[Slot, ...]) -> dict[str, Task]:
        return await self._tasks.get_many(frozenset(slot.task_id for slot in slots))

    async def get(self, day: date) -> DayPlan:
        return await self._plan_by_date(day)

    async def upsert(self, plan: DayPlan) -> DayPlan:
        # The date route owns identity: overwrite keeps the stored id so
        # merge() updates in place instead of colliding with the unique date.
        existing = await self._plans.get_by_date(plan.date)
        if existing is not None:
            plan = replace(plan, id=existing.id)
        tasks = await self._tasks_for(plan.slots)
        validate_day_plan(plan, tasks)
        await self._plans.save(plan)
        await self._session.flush()
        return plan

    async def move(self, day: date, pos_from: int, pos_to: int) -> DayPlan:
        plan = await self._plan_by_date(day)
        # move_slot is total on valid positions; errors are 422-bound.
        moved = move_slot(plan, pos_from, pos_to)
        await self._plans.save(moved)
        await self._session.flush()
        return moved
