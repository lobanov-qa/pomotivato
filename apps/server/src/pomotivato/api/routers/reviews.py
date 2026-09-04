"""Reviews router: one endpoint, FSM-authoritative rules behind it (spec 02 §5)."""

from __future__ import annotations

from fastapi import APIRouter, status

from pomotivato.api.deps import ClockDep, DbSession, RegistryDep
from pomotivato.api.schemas import ReviewCreateDto, ReviewDto
from pomotivato.services.review_service import ReviewService

router = APIRouter(prefix="/api/reviews", tags=["reviews"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ReviewDto)
async def create_review(
    dto: ReviewCreateDto,
    session: DbSession,
    clock: ClockDep,
    registry: RegistryDep,
) -> ReviewDto:
    service = ReviewService(session, clock, registry)
    review = await service.submit(dto.segment_id, dto.score, dto.comment)
    return ReviewDto.from_core(review)
