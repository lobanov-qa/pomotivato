"""Day-plan router: plan-per-date upsert, read and slot moves (spec 02 §5)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter

from pomotivato.api.deps import DbSession
from pomotivato.api.schemas import DayPlanDto, MoveSlotDto
from pomotivato.core.errors import ValidationError
from pomotivato.services.day_plan_service import DayPlanService

router = APIRouter(prefix="/api/day-plans", tags=["day-plans"])


@router.get("/{plan_date}", response_model=DayPlanDto)
async def get_day_plan(plan_date: date, session: DbSession) -> DayPlanDto:
    service = DayPlanService(session)
    return DayPlanDto.from_core(await service.get(plan_date))


@router.put("/{plan_date}", response_model=DayPlanDto)
async def put_day_plan(plan_date: date, dto: DayPlanDto, session: DbSession) -> DayPlanDto:
    service = DayPlanService(session)
    # The path date owns the plan; the body date must agree with it.
    if dto.date != plan_date:
        msg = f"body date {dto.date} != path date {plan_date}"
        raise ValidationError(msg)
    return DayPlanDto.from_core(await service.upsert(dto.to_core()))


@router.post("/{plan_date}/slots/move", response_model=DayPlanDto)
async def move_slot(plan_date: date, dto: MoveSlotDto, session: DbSession) -> DayPlanDto:
    service = DayPlanService(session)
    moved = await service.move(plan_date, dto.from_pos, dto.to_pos)
    return DayPlanDto.from_core(moved)
