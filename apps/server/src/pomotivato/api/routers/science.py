"""Hints + repetitions-queue routers (spec 05 §3.6-§3.7).

/api/hints answers the *live* moment: when a session runs, its phase and
the open block's burn are folded in (overlearning must fire while the
user over-invests, not after the tomato closes). /api/repetitions/due is
the spaced-repetition inbox: due rows joined with task titles, overdue
days computed server-side — the client renders, never calculates.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from pomotivato.api.deps import ClockDep, DbSession, RegistryDep
from pomotivato.api.schemas import HintDto, RepetitionDueDto
from pomotivato.core.models import SegmentPhase
from pomotivato.infra.repository import TaskRepository
from pomotivato.infra.repository_sessions import RepetitionRepository
from pomotivato.services.hints import due_on
from pomotivato.services.hints_service import HintService, LiveView
from pomotivato.services.session_service import SessionService

hints_router = APIRouter(prefix="/api", tags=["hints"])
reps_router = APIRouter(prefix="/api/repetitions", tags=["repetitions"])

BREAK_PHASES = frozenset(
    {
        SegmentPhase.BREAK.value,
        SegmentPhase.LONG_BREAK.value,
        SegmentPhase.SPECIAL_BREAK.value,
    }
)


@hints_router.get("/hints", response_model=list[HintDto])
async def get_hints(
    session: DbSession,
    clock: ClockDep,
    registry: RegistryDep,
    day: Annotated[date | None, Query()] = None,
) -> list[HintDto]:
    today = clock.now().date()
    live = LiveView()
    active_id = registry.latest_active()
    if active_id is not None:
        view = await SessionService(session, clock, registry).get_view(active_id)
        live.in_break = view.phase in BREAK_PHASES
        open_work = next(
            (
                seg
                for seg in reversed(view.timeline)
                if seg.ended_at is None and seg.phase is SegmentPhase.WORK
            ),
            None,
        )
        if open_work is not None:
            burn_sec = max(0, open_work.planned_min * 60 - view.remaining_sec)
            live.open_task_id = open_work.task_id
            live.open_minutes_spent = round(burn_sec / 60)
    hints = await HintService(session).hints_for_day(day or today, live)
    return [HintDto(kind=h.kind, params=h.params) for h in hints]


@reps_router.get("/due", response_model=list[RepetitionDueDto])
async def get_due_repetitions(
    session: DbSession,
    clock: ClockDep,
    as_of: Annotated[date | None, Query()] = None,
) -> list[RepetitionDueDto]:
    today = as_of or clock.now().date()
    queue = await RepetitionRepository(session).list_all()
    tasks = {task.id: task for task in await TaskRepository(session).list_all()}
    rows: list[RepetitionDueDto] = []
    for state in due_on(tuple(queue), today):
        task = tasks.get(state.task_id)
        if task is None:
            continue  # orphan queue row: the task is gone, nothing to show
        rows.append(
            RepetitionDueDto(
                task_id=state.task_id,
                title=task.title,
                interval_idx=state.interval_idx,
                next_due=state.next_due.isoformat(),
                overdue_days=max(0, (today - state.next_due).days),
            )
        )
    return rows
