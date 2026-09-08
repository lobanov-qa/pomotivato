"""DayPlanService: one plan per date, slots validated by core (spec 02 §4)."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from pomotivato.core.errors import ValidationError
from pomotivato.core.models import DayPlan, Slot, Task
from pomotivato.core.schedule import move_slot
from pomotivato.core.validation import validate_day_plan
from pomotivato.infra.errors import NotFoundError
from pomotivato.infra.repository import DayPlanRepository, TaskRepository
from pomotivato.services.planner import AddOutcome, activate_recurring, add_task_to_plan


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

    async def add(self, day: date, task_id: str, today: date) -> tuple[DayPlan, AddOutcome]:
        """Append one task's chunk to the date's plan (spec 05 §3.8).

        Past dates are refused (⚑ Q4): yesterday is not a planning surface.
        Unknown task -> 404 via NotFoundError; the running session is
        unaffected — it runs on its start() snapshot (GWT-M4).
        """
        if day < today:
            msg = f"day plan for {day.isoformat()} is in the past"
            raise ValidationError(msg)
        task = await self._tasks.get(task_id)
        if task is None:
            msg = f"task {task_id!r} not found"
            raise NotFoundError(msg)
        plan = await self._ensure_plan(day)
        outcome = add_task_to_plan(plan, task)
        await self._persist(outcome.plan)
        return outcome.plan, outcome

    async def activate(self, day: date, today: date) -> tuple[DayPlan, AddOutcome]:
        """Materialize every recurring task into the date's plan (§3.2)."""
        if day < today:
            msg = f"day plan for {day.isoformat()} is in the past"
            raise ValidationError(msg)
        plan = await self._ensure_plan(day)
        outcome = activate_recurring(plan, await self._tasks.list_all(), day)
        await self._persist(outcome.plan)
        return outcome.plan, outcome

    async def remove_slot(self, day: date, sector: int, today: date) -> DayPlan:
        """Take one task off the day (spec 06 DF1: the week screen's ×).

        Past dates are refused (⚑ Q4); an unknown sector is a no-op return
        so a double-click cannot 500. The emptied plan goes away with the
        last slot (clear semantics), so the day stops claiming it.
        """
        if day < today:
            msg = f"day plan for {day.isoformat()} is in the past"
            raise ValidationError(msg)
        plan = await self._plan_by_date(day)
        kept = tuple(
            Slot(sector=index + 1, task_id=slot.task_id)
            for index, slot in enumerate(s for s in plan.slots if s.sector != sector)
        )
        if len(kept) == len(plan.slots):
            return plan
        if not kept:
            await self._plans.drop_or_empty(plan)
            await self._session.flush()
            return replace(plan, slots=())
        await self._persist(replace(plan, slots=kept))
        return replace(plan, slots=kept)

    async def clear(self, day: date, today: date) -> None:
        """Forget the day's plan entirely (spec 06 DF1: empty doing-column).

        The kanban derives today's plan from the doing column; when it
        empties, the leftover slots are ghosts that block the cards'
        deletion. Past dates stay untouched (⚑ Q4).
        """
        if day < today:
            msg = f"day plan for {day.isoformat()} is in the past"
            raise ValidationError(msg)
        plan = await self._plans.get_by_date(day)
        if plan is not None:
            await self._plans.drop_or_empty(plan)
            await self._session.flush()

    async def _ensure_plan(self, day: date) -> DayPlan:
        plan = await self._plans.get_by_date(day)
        if plan is None:
            # A missing date gets an in-memory empty plan: add/activate
            # fill the first sector below, and _persist validates before
            # writing, so an empty row can never reach storage (core V9).
            plan = DayPlan(id=f"plan-{day.isoformat()}", date=day, slots=())
        return plan

    async def _persist(self, plan: DayPlan) -> None:
        tasks = await self._tasks_for(plan.slots)
        validate_day_plan(plan, tasks)
        await self._plans.save(plan)
        await self._session.flush()
