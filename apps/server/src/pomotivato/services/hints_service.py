"""HintService: reading glue for GET /api/hints (spec 05 §3.6).

Loads one day's rows (plan, its sessions' segments, the task catalog and
settings) and hands everything to the pure `compute_hints`. The live
session is NOT touched here: the router passes its phase/open-task view
in, so this service stays DB-only and the FSM stays in its own layer.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from pomotivato.core.models import Segment, SegmentPhase, SegmentStatus
from pomotivato.infra.repository import DayPlanRepository, TaskRepository
from pomotivato.infra.repository_sessions import (
    RepetitionRepository,
    SegmentRepository,
    SessionRepository,
)
from pomotivato.services.blocks import completed_work_blocks
from pomotivato.services.hints import Hint, compute_hints, due_on
from pomotivato.services.settings_service import SettingsService


class LiveView:
    """The router's snapshot of the running FSM for hint rules.

    `in_break` — the current phase is a rest phase; `open_task_id` — the
    WORK the user is inside right now (overlearning watches its burn);
    `next_task_id` — the unplayed sector the ladder opens next (DF28: the
    frog hint may only promise what the frozen dial can actually play).
    """

    def __init__(
        self,
        in_break: bool = False,
        open_task_id: str | None = None,
        open_minutes_spent: int = 0,
        next_task_id: str | None = None,
    ) -> None:
        self.in_break = in_break
        self.open_task_id = open_task_id
        self.open_minutes_spent = open_minutes_spent
        self.next_task_id = next_task_id


class HintService:
    """Project today's (or a given day's) rows into hint kinds."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._plans = DayPlanRepository(session)
        self._tasks = TaskRepository(session)
        self._sessions = SessionRepository(session)
        self._segments = SegmentRepository(session)
        self._settings = SettingsService(session)
        self._repetitions = RepetitionRepository(session)

    async def hints_for_day(self, day: date, live: LiveView) -> tuple[Hint, ...]:
        plan = await self._plans.get_by_date(day)
        segments: list[Segment] = []
        if plan is not None:
            for model in await self._sessions.get_many_for_plan(plan.id):
                segments += list(await self._segments.get_many_for_session(model.id))
        blocks = tuple(
            block for block in completed_work_blocks(tuple(segments)) if block.day == day
        )
        interrupted = tuple(
            segment.task_id
            for segment in segments
            if segment.phase is SegmentPhase.WORK
            and segment.status is SegmentStatus.INTERRUPTED
            and segment.task_id is not None
        )
        tasks_by_id = {task.id: task for task in await self._tasks.list_all()}
        settings = await self._settings.get_session_settings()
        plan_ids = frozenset(slot.task_id for slot in plan.slots) if plan else frozenset()
        # DF28: the ladder's due rows are plain data for the pure rule —
        # the queue read lives here, the "which line to show" decision in
        # compute_hints. Rows of gone cards would surprise the browser.
        due_recall = frozenset(
            state.task_id
            for state in due_on(tuple(await self._repetitions.list_all()), day)
            if state.task_id in tasks_by_id
        )
        return compute_hints(
            day_blocks=blocks,
            interrupted_task_ids=interrupted,
            tasks_by_id=tasks_by_id,
            plan_task_ids=plan_ids,
            in_break=live.in_break,
            settings=settings,
            open_task_id=live.open_task_id,
            open_minutes_spent=live.open_minutes_spent,
            next_task_id=live.next_task_id,
            due_recall_task_ids=due_recall,
        )
