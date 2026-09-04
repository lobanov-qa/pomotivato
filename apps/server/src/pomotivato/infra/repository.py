"""Repositories: the ORM <-> pure-core boundary (spec 02 §4).

One class per aggregate root; they speak core dataclasses and know nothing
about HTTP or service rules. JSON columns are (de)serialized only with the
core helpers, so the wire format keeps a single owner (DRY).
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pomotivato.core.models import (
    DayPlan,
    Task,
    TaskStatus,
    TaskType,
    day_plan_from_dict,
    recurrence_to_dict,
    task_from_dict,
    to_dict,
)
from pomotivato.infra.orm import DayPlanRow, SettingRow, TaskRow


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

    async def dates_referencing(self, task_id: str) -> tuple[date, ...]:
        """Dates whose plan still places this task in a slot.

        Slots live in one JSON column, so the scan is in Python: a
        desktop-scale table (one row per day) makes LIKE hacks KISS-over.
        """
        rows = await self._session.scalars(select(DayPlanRow))
        return tuple(
            date.fromisoformat(row.date)
            for row in rows
            if any(slot.task_id == task_id for slot in _plan_from_row(row).slots)
        )


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
