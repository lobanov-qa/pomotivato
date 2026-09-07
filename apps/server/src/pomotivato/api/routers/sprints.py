"""Sprint router: thin period CRUD (spec 05 §3.10, ADR-0003 p.3).

GET lists newest-first (the /week band reads items[0] as active-or-none);
POST assigns number=max+1; PATCH carries texts/period/status — activation
conflicts and overlaps answer 409 via the shared error envelope.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from pomotivato.api.deps import DbSession
from pomotivato.api.schemas import SprintCreateDto, SprintDto, SprintPatchDto
from pomotivato.services.sprint_service import SprintService

router = APIRouter(prefix="/api/sprints", tags=["sprints"])


@router.get("", response_model=list[SprintDto])
async def list_sprints(session: DbSession) -> list[SprintDto]:
    service = SprintService(session)
    return [SprintDto.from_core(sprint) for sprint in await service.list()]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=SprintDto)
async def create_sprint(dto: SprintCreateDto, session: DbSession) -> SprintDto:
    service = SprintService(session)
    sprint = await service.create(
        name=dto.name,
        goal=dto.goal,
        done_criteria=dto.done_criteria,
        start_date=dto.start_date,
        end_date=dto.end_date,
    )
    return SprintDto.from_core(sprint)


@router.patch("/{sprint_id}", response_model=SprintDto)
async def patch_sprint(sprint_id: str, dto: SprintPatchDto, session: DbSession) -> SprintDto:
    service = SprintService(session)
    return SprintDto.from_core(await service.patch(sprint_id, dto.changes()))
