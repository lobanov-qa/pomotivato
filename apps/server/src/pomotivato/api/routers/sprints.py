"""Sprint router: container lifecycle over SprintService (spec 07 §6).

GET lists newest-first with server-computed fate counts and the is_current
flag (the "!" badge and the star must agree across windows); GET /{id}
embeds the owned cards (the sprint modal reads them from one request);
PATCH carries texts/period/status through the same error envelope; DELETE
erases the container with its cards (V29); carry-choice-all freezes every
still-undecided unfinished card (the "Оставить все как есть" button, A40).
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from pomotivato.api.deps import ClockDep, DbSession
from pomotivato.api.schemas import (
    CarryAllResultDto,
    SprintCreateDto,
    SprintDetailDto,
    SprintDto,
    SprintPatchDto,
    TaskDto,
)
from pomotivato.core.models import SprintStatus
from pomotivato.services.sprint_service import SprintService

router = APIRouter(prefix="/api/sprints", tags=["sprints"])

StatusParam = Annotated[SprintStatus | None, Query()]


@router.get("", response_model=list[SprintDto])
async def list_sprints(
    session: DbSession, clock: ClockDep, status: StatusParam = None
) -> list[SprintDto]:
    service = SprintService(session, clock)
    sprints = await service.list(status=status)
    unfinished, pending = await service.fate_counts()
    today = clock.now().date()
    return [
        SprintDto.from_core(
            sprint,
            unfinished=unfinished.get(sprint.id, 0),
            pending=pending.get(sprint.id, 0),
            is_current=sprint.covers(today),
        )
        for sprint in sprints
    ]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=SprintDto)
async def create_sprint(dto: SprintCreateDto, session: DbSession, clock: ClockDep) -> SprintDto:
    service = SprintService(session, clock)
    sprint = await service.create(
        name=dto.name,
        goal=dto.goal,
        done_criteria=dto.done_criteria,
        start_date=dto.start_date,
        end_date=dto.end_date,
    )
    return SprintDto.from_core(sprint)


@router.get("/{sprint_id}", response_model=SprintDetailDto)
async def get_sprint(sprint_id: str, session: DbSession, clock: ClockDep) -> SprintDetailDto:
    service = SprintService(session, clock)
    tasks = await service.tasks_of(sprint_id)
    base = SprintDto.from_core(await service.get(sprint_id))
    return SprintDetailDto(**base.model_dump(), tasks=[TaskDto.from_core(t) for t in tasks])


@router.patch("/{sprint_id}", response_model=SprintDto)
async def patch_sprint(
    sprint_id: str, dto: SprintPatchDto, session: DbSession, clock: ClockDep
) -> SprintDto:
    service = SprintService(session, clock)
    return SprintDto.from_core(await service.patch(sprint_id, dto.changes()))


@router.delete("/{sprint_id}", status_code=204)
async def delete_sprint(sprint_id: str, session: DbSession, clock: ClockDep) -> Response:
    service = SprintService(session, clock)
    await service.delete(sprint_id)
    return Response(status_code=HTTPStatus.NO_CONTENT)


@router.post("/{sprint_id}/carry-choice-all", response_model=CarryAllResultDto)
async def carry_choice_all(
    sprint_id: str, session: DbSession, clock: ClockDep
) -> CarryAllResultDto:
    service = SprintService(session, clock)
    decided = await service.leave_all_open(sprint_id)
    return CarryAllResultDto(decided=decided)
