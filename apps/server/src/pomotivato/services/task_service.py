"""TaskService: the kanban card use-cases (spec 02 §4).

All domain rules are enforced by pomotivato.core validators; this service
only sequences reads/writes and turns core outcomes into infra errors.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from pomotivato.core.errors import StatusTransitionError, ValidationError
from pomotivato.core.models import Task, TaskStatus, TaskType
from pomotivato.core.validation import (
    validate_deadline_realism,
    validate_planning_ready,
    validate_status_transition,
    validate_task,
)
from pomotivato.infra.errors import ConflictError, NotFoundError
from pomotivato.infra.repository import DayPlanRepository, TaskRepository
from pomotivato.services.settings_service import SettingsService

# Fields PATCH may touch; everything else is identity or derived.
_PATCHABLE_FIELDS = frozenset(
    {
        "title",
        "type",
        "important",
        "urgent",
        "estimate_blocks",
        "deadline",
        "parent_id",
        "when_then",
        "done_criteria",
        "benefit",
        "no_timer",
    }
)


class TaskService:
    """Create, read, patch, transition and delete task cards."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._tasks = TaskRepository(session)
        self._day_plans = DayPlanRepository(session)
        self._settings = SettingsService(session)

    async def create(self, task: Task) -> Task:
        validate_task(task)
        validate_deadline_realism(task)
        if await self._tasks.get(task.id) is not None:
            msg = f"task {task.id!r} already exists"
            raise ConflictError(msg)
        parent = task.parent_id
        if parent is not None and await self._tasks.get(parent) is None:
            msg = f"parent task {parent!r} does not exist"
            raise NotFoundError(msg)
        await self._tasks.add(task)
        await self._session.flush()
        return task

    async def get(self, task_id: str) -> Task:
        task = await self._tasks.get(task_id)
        if task is None:
            msg = f"task {task_id!r} not found"
            raise NotFoundError(msg)
        return task

    async def list(
        self,
        *,
        status: TaskStatus | None = None,
        task_type: TaskType | None = None,
        parent_id: str | None = None,
    ) -> tuple[Task, ...]:
        return await self._tasks.list(status=status, task_type=task_type, parent_id=parent_id)

    async def patch(self, task_id: str, changes: dict[str, Any]) -> Task:
        unknown = changes.keys() - _PATCHABLE_FIELDS
        if unknown:
            msg = f"cannot update fields: {sorted(unknown)}"
            raise ValidationError(msg)
        task = await self.get(task_id)
        updated = replace(task, **changes)
        validate_task(updated)
        validate_deadline_realism(updated)
        if updated.parent_id is not None and updated.parent_id != task_id:
            if await self._tasks.get(updated.parent_id) is None:
                msg = f"parent task {updated.parent_id!r} does not exist"
                raise NotFoundError(msg)
        elif updated.parent_id == task_id:
            msg = "task cannot be its own parent"
            raise ValidationError(msg)
        await self._tasks.put(updated)
        await self._session.flush()
        return updated

    async def set_status(self, task_id: str, new_status: TaskStatus) -> Task:
        task = await self.get(task_id)
        try:
            validate_status_transition(task.status, new_status)
        except StatusTransitionError as err:
            raise ConflictError(str(err)) from err
        if new_status is TaskStatus.PLANNED:
            require = await self._settings.require_science_fields()
            validate_planning_ready(task, require)
        if new_status is TaskStatus.DOING and task.status is not TaskStatus.DOING:
            # Funnel law: "В работе" == today == the dial; the capacity is
            # a server-side gate so no client (or second window) overflows.
            # DF13: no-timer errands don't consume the dial — free to carry.
            limit = (await self._settings.get_ui_settings()).max_in_work
            in_work = await self._tasks.list(status=TaskStatus.DOING)
            timer_load = sum(1 for t in in_work if not t.no_timer)
            if not task.no_timer and timer_load >= limit:
                msg = f"only {limit} tasks fit in work today"
                raise ConflictError(msg)
        updated = replace(task, status=new_status)
        await self._tasks.put(updated)
        await self._session.flush()
        return updated

    async def clone(self, task_id: str, clone_id: str) -> Task:
        """Duplicate a finished card back into the backlog (spec 06 DF12).

        The point (author 08.09) is not re-creating a big repeated task
        from scratch: title, type, quadrant, chunk, when_then/criteria/
        benefit and recurrence cadence all carry over. What resets:
        status -> backlog, deadline -> None (a past date must not haunt
        the copy), and `cloned_from` records the lineage for history.
        """
        task = await self.get(task_id)
        if await self._tasks.get(clone_id) is not None:
            msg = f"task {clone_id!r} already exists"
            raise ConflictError(msg)
        clone = replace(
            task,
            id=clone_id,
            status=TaskStatus.BACKLOG,
            deadline=None,
            cloned_from=task.id,
        )
        validate_task(clone)
        await self._tasks.add(clone)
        await self._session.flush()
        return clone

    async def delete(self, task_id: str) -> None:
        task = await self.get(task_id)
        # Q3 of spec 02: only cards that never entered work are forgettable.
        if task.status not in (TaskStatus.BACKLOG, TaskStatus.ARCHIVED):
            msg = f"only backlog/archived tasks can be deleted, {task.status.value} survives"
            raise ConflictError(msg)
        if await self._tasks.has_children(task_id):
            msg = f"task {task_id!r} still has children"
            raise ConflictError(msg)
        # DF1 of spec 06 (author 08.09, second pass): a backlog card owns
        # no future — every slot referencing it, past or planned, is its
        # shadow and is swept first; worked segments detach, not vanish.
        await self._day_plans.purge_task_references(task_id)
        await self._tasks.detach_history(task_id)
        await self._tasks.delete(task_id)
        await self._session.flush()
