"""Sprint router: named date-period containers (spec 07, ADR-0005).

GET lists newest-first (the /week band reads items[0] as active-or-none);
POST assigns number=max+1 and refuses retrospective periods (V19 creation);
PATCH carries texts/period/status — activation conflicts and overlaps answer
409 via the shared error envelope.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from pomotivato.api.deps import ClockDep, DbSession
from pomotivato.api.schemas import SprintCreateDto, SprintDto, SprintPatchDto
from pomotivato.services.sprint_service import SprintService

router = APIRouter(prefix="/api/sprints", tags=["sprints"])


@router.get("", response_model=list[SprintDto])
async def list_sprints(session: DbSession, clock: ClockDep) -> list[SprintDto]:
    service = SprintService(session, clock)
    return [SprintDto.from_core(sprint) for sprint in await service.list()]


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


@router.patch("/{sprint_id}", response_model=SprintDto)
async def patch_sprint(
    sprint_id: str, dto: SprintPatchDto, session: DbSession, clock: ClockDep
) -> SprintDto:
    service = SprintService(session, clock)
    return SprintDto.from_core(await service.patch(sprint_id, dto.changes()))
