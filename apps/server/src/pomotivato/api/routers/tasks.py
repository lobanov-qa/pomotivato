"""Tasks router: kanban cards over TaskService (spec 02 §5)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Response

from pomotivato.api.deps import ClockDep, DbSession
from pomotivato.api.schemas import SetStatusDto, TaskCreateDto, TaskDto, TaskPatchDto
from pomotivato.core.models import TaskStatus, TaskType
from pomotivato.services.task_service import TaskService

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

StatusFilter = Annotated[TaskStatus | None, Query()]
TypeFilter = Annotated[TaskType | None, Query()]
ParentFilter = Annotated[str | None, Query()]


@router.post("", status_code=201, response_model=TaskDto)
async def create_task(dto: TaskCreateDto, session: DbSession, clock: ClockDep) -> TaskDto:
    service = TaskService(session)
    task = await service.create(dto.to_core(clock.now()))
    return TaskDto.from_core(task)


@router.get("", response_model=list[TaskDto])
async def list_tasks(
    session: DbSession,
    status: StatusFilter = None,
    type: TypeFilter = None,
    parent_id: ParentFilter = None,
) -> list[TaskDto]:
    service = TaskService(session)
    tasks = await service.list(status=status, task_type=type, parent_id=parent_id)
    return [TaskDto.from_core(task) for task in tasks]


@router.get("/{task_id}", response_model=TaskDto)
async def get_task(task_id: str, session: DbSession) -> TaskDto:
    service = TaskService(session)
    return TaskDto.from_core(await service.get(task_id))


@router.patch("/{task_id}", response_model=TaskDto)
async def patch_task(task_id: str, dto: TaskPatchDto, session: DbSession) -> TaskDto:
    service = TaskService(session)
    return TaskDto.from_core(await service.patch(task_id, dto.changes()))


@router.post("/{task_id}/status", response_model=TaskDto)
async def set_task_status(task_id: str, dto: SetStatusDto, session: DbSession) -> TaskDto:
    service = TaskService(session)
    return TaskDto.from_core(await service.set_status(task_id, dto.to))


@router.delete("/{task_id}", status_code=204)
async def delete_task(task_id: str, session: DbSession) -> Response:
    service = TaskService(session)
    await service.delete(task_id)
    return Response(status_code=204)
