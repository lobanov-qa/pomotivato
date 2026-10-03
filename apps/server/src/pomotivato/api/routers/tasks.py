"""Tasks router: kanban cards over TaskService (spec 02 §5, spec 07 §6)."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Response

from pomotivato.api.deps import ClockDep, DbSession
from pomotivato.api.schemas import (
    CarryChoiceDto,
    SetStatusDto,
    TaskCloneDto,
    TaskCreateDto,
    TaskDto,
    TaskPatchDto,
)
from pomotivato.core.days import close_eligible, future_ticks, missed_ticks
from pomotivato.core.models import TaskStatus, TaskType
from pomotivato.infra.repository_sessions import SegmentRepository
from pomotivato.services.task_service import TaskService

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

StatusFilter = Annotated[TaskStatus | None, Query()]
TypeFilter = Annotated[TaskType | None, Query()]
ParentFilter = Annotated[str | None, Query()]
# Spec 07 §6: the board reads one scope at a time — a sprint container, or
# the dateless shelf via no_sprint (client sends both as separate queries).
SprintFilter = Annotated[str | None, Query()]
NoSprintFilter = Annotated[bool, Query()]


@router.post("", status_code=201, response_model=TaskDto)
async def create_task(dto: TaskCreateDto, session: DbSession, clock: ClockDep) -> TaskDto:
    service = TaskService(session, clock)
    task = await service.create(dto.to_core(clock.now()))
    return TaskDto.from_core(task)


@router.get("", response_model=list[TaskDto])
async def list_tasks(
    session: DbSession,
    clock: ClockDep,
    status: StatusFilter = None,
    type: TypeFilter = None,
    parent_id: ParentFilter = None,
    sprint_id: SprintFilter = None,
    no_sprint: NoSprintFilter = False,
) -> list[TaskDto]:
    service = TaskService(session, clock)
    await service.fold_yesterday()  # V30+V33: the lazy day fold on first read
    tasks = await service.list(
        status=status, task_type=type, parent_id=parent_id, sprint_id=sprint_id, no_sprint=no_sprint
    )
    # DF10: one grouped segment scan powers the card dots on the whole board —
    # carried per task, the client never counts history itself. The dots read
    # the worked-day count (author 23.09), the block count feeds the day math.
    # E4c PR 4 adds the §4.7 hint inputs (missed/left ticks, closeable) from
    # the SAME scans: the panel explains the card without re-deriving anything.
    segments = SegmentRepository(session)
    done = await segments.done_work_by_task()
    last = await segments.last_work_by_task()
    worked = await segments.worked_days_by_task()
    today = clock.now().date()
    empty_days: frozenset[date] = frozenset()
    return [
        TaskDto.from_core(
            task,
            blocks_done=done.get(task.id, 0),
            last_worked=last.get(task.id),
            days_done=task.ticked_days_worked(worked.get(task.id, empty_days)),
            days_missed=[
                day.isoformat()
                for day in missed_ticks(task, today, worked.get(task.id, empty_days))
            ],
            days_left=[day.isoformat() for day in future_ticks(task, today)],
            # The hint only offers closing for a card that can still walk in.
            closeable=task.status not in (TaskStatus.DONE, TaskStatus.ARCHIVED)
            and close_eligible(task, today, worked.get(task.id, empty_days)),
        )
        for task in tasks
    ]


@router.get("/{task_id}", response_model=TaskDto)
async def get_task(task_id: str, session: DbSession, clock: ClockDep) -> TaskDto:
    service = TaskService(session, clock)
    return TaskDto.from_core(await service.get(task_id))


@router.patch("/{task_id}", response_model=TaskDto)
async def patch_task(
    task_id: str, dto: TaskPatchDto, session: DbSession, clock: ClockDep
) -> TaskDto:
    service = TaskService(session, clock)
    return TaskDto.from_core(await service.patch(task_id, dto.changes()))


@router.post("/{task_id}/status", response_model=TaskDto)
async def set_task_status(
    task_id: str, dto: SetStatusDto, session: DbSession, clock: ClockDep
) -> TaskDto:
    service = TaskService(session, clock)
    return TaskDto.from_core(await service.set_status(task_id, dto.to))


@router.post("/{task_id}/clone", response_model=TaskDto, status_code=201)
async def clone_task(
    task_id: str, dto: TaskCloneDto, session: DbSession, clock: ClockDep
) -> TaskDto:
    service = TaskService(session, clock)
    return TaskDto.from_core(await service.clone(task_id, dto.id))


@router.post("/{task_id}/close", response_model=TaskDto)
async def close_task(task_id: str, session: DbSession, clock: ClockDep) -> TaskDto:
    """V32/A35: the dialog's "Перевести в «Готово»" (server re-checks)."""
    service = TaskService(session, clock)
    return TaskDto.from_core(await service.close(task_id))


@router.post("/{task_id}/carry-choice", response_model=TaskDto)
async def carry_choice(
    task_id: str, dto: CarryChoiceDto, session: DbSession, clock: ClockDep
) -> TaskDto:
    """A40/V34: the per-card fate menu (target active sprint / shelf / leave)."""
    service = TaskService(session, clock)
    leave, target = dto.decision()
    task = await service.resolve_carry(
        task_id, target_sprint_id=target, leave=leave, today=clock.now().date()
    )
    return TaskDto.from_core(task)


@router.delete("/{task_id}", status_code=204)
async def delete_task(task_id: str, session: DbSession, clock: ClockDep) -> Response:
    service = TaskService(session, clock)
    await service.delete(task_id)
    return Response(status_code=204)
