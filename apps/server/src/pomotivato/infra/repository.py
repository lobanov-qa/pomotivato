"""Repositories: the ORM <-> pure-core boundary (spec 02 §4).

One class per aggregate root; they speak core dataclasses and know nothing
about HTTP or service rules. JSON columns are (de)serialized only with the
core helpers, so the wire format keeps a single owner (DRY).
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime
from typing import Any

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from pomotivato.core.models import (
    DayPlan,
    Sprint,
    SprintStatus,
    Task,
    TaskStatus,
    TaskType,
    day_plan_from_dict,
    recurrence_to_dict,
    sprint_from_dict,
    task_from_dict,
    to_dict,
)
from pomotivato.infra.orm import (
    DayPlanRow,
    RepetitionRow,
    SegmentRow,
    SessionRow,
    SettingRow,
    SprintRow,
    TaskRow,
)


def _iso(value: date | datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _task_to_row(task: Task) -> TaskRow:
    return TaskRow(
        id=task.id,
        title=task.title,
        type=task.type.value,
        important=task.important,
        urgent=task.urgent,
        status=task.status.value,
        estimate_blocks=task.estimate_blocks,
        deadline=_iso(task.deadline),
        parent_id=task.parent_id,
        recurrence_json=json.dumps(recurrence_to_dict(task.recurrence)),
        when_then=task.when_then,
        done_criteria=task.done_criteria,
        benefit=task.benefit,
        cloned_from=task.cloned_from,
        no_timer=task.no_timer,
        created_at=task.created_at.isoformat(),
    )


def _task_from_row(row: TaskRow) -> Task:
    data: dict[str, Any] = {
        "id": row.id,
        "title": row.title,
        "type": row.type,
        "important": row.important,
        "urgent": row.urgent,
        "status": row.status,
        "estimate_blocks": row.estimate_blocks,
        "deadline": row.deadline,
        "parent_id": row.parent_id,
        "recurrence": json.loads(row.recurrence_json),
        "when_then": row.when_then,
        "done_criteria": row.done_criteria,
        "benefit": row.benefit,
        "cloned_from": row.cloned_from,
        "no_timer": bool(row.no_timer),
        "created_at": row.created_at,
    }
    return task_from_dict(data)


class TaskRepository:
    """Persistence for the tasks table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, task: Task) -> None:
        self._session.add(_task_to_row(task))

    async def put(self, task: Task) -> None:
        await self._session.merge(_task_to_row(task))

    async def get(self, task_id: str) -> Task | None:
        row = await self._session.get(TaskRow, task_id)
        return None if row is None else _task_from_row(row)

    async def get_many(self, task_ids: frozenset[str]) -> dict[str, Task]:
        if not task_ids:
            return {}
        stmt = select(TaskRow).where(TaskRow.id.in_(sorted(task_ids)))
        rows = await self._session.scalars(stmt)
        return {row.id: _task_from_row(row) for row in rows}

    async def list(
        self,
        *,
        status: TaskStatus | None = None,
        task_type: TaskType | None = None,
        parent_id: str | None = None,
    ) -> tuple[Task, ...]:
        # ISO UTC strings sort chronologically, so TEXT order is safe here.
        stmt = select(TaskRow).order_by(TaskRow.created_at, TaskRow.id)
        if status is not None:
            stmt = stmt.where(TaskRow.status == status.value)
        if task_type is not None:
            stmt = stmt.where(TaskRow.type == task_type.value)
        if parent_id is not None:
            stmt = stmt.where(TaskRow.parent_id == parent_id)
        rows = await self._session.scalars(stmt)
        return tuple(_task_from_row(row) for row in rows)

    async def list_all(self) -> tuple[Task, ...]:
        """All tasks (dashboard scans are desktop-scale, spec 04 §4)."""
        rows = await self._session.scalars(select(TaskRow).order_by(TaskRow.id))
        return tuple(_task_from_row(row) for row in rows)

    async def detach_history(self, task_id: str) -> None:
        """DF1: forget a card without erasing the worked time behind it.

        Completed timer segments keep their numbers but lose the link to
        the card (stats already tolerate NULL task ids); the spaced-
        repetition queue row is pure future-state and goes away with it.
        """
        await self._session.execute(
            sa_update(SegmentRow).where(SegmentRow.task_id == task_id).values(task_id=None)
        )
        await self._session.execute(
            sa_delete(RepetitionRow).where(RepetitionRow.task_id == task_id)
        )

    async def has_children(self, task_id: str) -> bool:
        stmt = select(TaskRow.id).where(TaskRow.parent_id == task_id).limit(1)
        child_id = await self._session.scalar(stmt)
        return child_id is not None

    async def delete(self, task_id: str) -> None:
        row = await self._session.get(TaskRow, task_id)
        if row is not None:
            await self._session.delete(row)


def _plan_to_row(plan: DayPlan) -> DayPlanRow:
    return DayPlanRow(
        id=plan.id,
        date=plan.date.isoformat(),
        slots_json=json.dumps([to_dict(slot) for slot in plan.slots]),
    )


def _plan_from_row(row: DayPlanRow) -> DayPlan:
    raw_slots: list[dict[str, Any]] = json.loads(row.slots_json)
    return day_plan_from_dict({"id": row.id, "date": row.date, "slots": raw_slots})


class DayPlanRepository:
    """Persistence for the day_plans table (one plan per date, unique)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, plan: DayPlan) -> None:
        await self._session.merge(_plan_to_row(plan))

    async def get_by_date(self, day: date) -> DayPlan | None:
        stmt = select(DayPlanRow).where(DayPlanRow.date == day.isoformat())
        row = await self._session.scalar(stmt)
        return None if row is None else _plan_from_row(row)

    async def get(self, plan_id: str) -> DayPlan | None:
        row = await self._session.get(DayPlanRow, plan_id)
        return None if row is None else _plan_from_row(row)

    async def list_all(self) -> tuple[DayPlan, ...]:
        """Every saved plan, by date (export scans the full history)."""
        rows = await self._session.scalars(select(DayPlanRow).order_by(DayPlanRow.date))
        return tuple(_plan_from_row(row) for row in rows)

    async def purge_task_references(self, task_id: str) -> tuple[date, ...]:
        """Drop this task's slots from every plan, past or future (spec 06 DF1).

        A backlog card owns no future: whatever still names it is its own
        shadow, swept with the card in the same transaction. A plan emptied
        by the purge loses its row unless session history still points at
        it (FK) — then the row survives as an empty shell. Returns purged
        dates for the caller to log.
        """
        rows = await self._session.scalars(select(DayPlanRow))
        purged: list[date] = []
        for row in rows:
            plan = _plan_from_row(row)
            kept = tuple(slot for slot in plan.slots if slot.task_id != task_id)
            if len(kept) == len(plan.slots):
                continue
            if kept:
                await self.save(replace(plan, slots=kept))
            else:
                await self.drop_or_empty(plan)
            purged.append(date.fromisoformat(row.date))
        await self._session.flush()
        return tuple(purged)

    async def has_session_references(self, plan_id: str) -> bool:
        """Does any stored session still point at this plan row (FK guard)?"""
        stmt = select(SessionRow.id).where(SessionRow.day_plan_id == plan_id).limit(1)
        return await self._session.scalar(stmt) is not None

    async def drop_or_empty(self, plan: DayPlan) -> None:
        """Delete the row when safe; otherwise keep it with zero slots.

        V9 forbids empty plans on the write surface (upsert), but history
        pins some rows: an empty shell is the honest compromise.
        """
        if await self.has_session_references(plan.id):
            await self.save(replace(plan, slots=()))
        else:
            row = await self._session.get(DayPlanRow, plan.id)
            if row is not None:
                await self._session.delete(row)


class SettingRepository:
    """Key/value store for app settings (JSON-encoded values)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, key: str) -> str | None:
        stmt = select(SettingRow.value).where(SettingRow.key == key)
        raw = await self._session.scalar(stmt)
        return None if raw is None else str(raw)

    async def set(self, key: str, value: str) -> None:
        await self._session.merge(SettingRow(key=key, value=value))


def _sprint_to_row(sprint: Sprint) -> SprintRow:
    return SprintRow(
        id=sprint.id,
        number=sprint.number,
        name=sprint.name,
        start_date=sprint.start_date.isoformat(),
        end_date=sprint.end_date.isoformat(),
        goal=sprint.goal,
        done_criteria=sprint.done_criteria,
        status=sprint.status.value,
    )


def _sprint_from_row(row: SprintRow) -> Sprint:
    return sprint_from_dict(
        {
            "id": row.id,
            "number": row.number,
            "name": row.name,
            "start_date": row.start_date,
            "end_date": row.end_date,
            "goal": row.goal,
            "done_criteria": row.done_criteria,
            "status": row.status,
        }
    )


class SprintRepository:
    """Persistence for the sprints table (ADR-0003 p.3).

    Dates are ISO TEXT, so overlap is plain lexicographic comparison:
    intervals [a,b] and [c,d] intersect iff a <= d and c <= b.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, sprint: Sprint) -> None:
        self._session.add(_sprint_to_row(sprint))

    async def put(self, sprint: Sprint) -> None:
        await self._session.merge(_sprint_to_row(sprint))

    async def get(self, sprint_id: str) -> Sprint | None:
        row = await self._session.get(SprintRow, sprint_id)
        return None if row is None else _sprint_from_row(row)

    async def list(self) -> tuple[Sprint, ...]:
        stmt = select(SprintRow).order_by(SprintRow.number.desc())
        rows = await self._session.scalars(stmt)
        return tuple(_sprint_from_row(row) for row in rows)

    async def max_number(self) -> int:
        stmt = select(func.max(SprintRow.number))
        current = await self._session.scalar(stmt)
        return int(current or 0)

    async def get_active(self) -> Sprint | None:
        stmt = select(SprintRow).where(SprintRow.status == SprintStatus.ACTIVE.value)
        row = await self._session.scalars(stmt)
        found = row.first()
        return None if found is None else _sprint_from_row(found)

    async def overlapping(
        self, start: date, end: date, exclude_id: str | None = None
    ) -> tuple[Sprint, ...]:
        """Open sprints (planned/active) whose period touches [start, end].

        Completed sprints are history: ADR-0003 lets a new period overlap
        them (⚑ Q9, author-approved 07.09).
        """
        stmt = select(SprintRow).where(
            SprintRow.status != SprintStatus.COMPLETED.value,
            SprintRow.start_date <= end.isoformat(),
            SprintRow.end_date >= start.isoformat(),
        )
        if exclude_id is not None:
            stmt = stmt.where(SprintRow.id != exclude_id)
        rows = await self._session.scalars(stmt)
        return tuple(_sprint_from_row(row) for row in rows)
