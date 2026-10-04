"""Day-plan router: plan-per-date upsert, read and slot moves (spec 02 §5)."""

from __future__ import annotations

from datetime import date
from http import HTTPStatus

from fastapi import APIRouter, Response

from pomotivato.api.deps import ClockDep, DbSession
from pomotivato.api.schemas import (
    AddResultDto,
    DayPlanAddDto,
    DayPlanDto,
    MoveSlotDto,
    RefreshResultDto,
    RefreshStatusDto,
)
from pomotivato.core.errors import ValidationError
from pomotivato.services.day_plan_service import DayPlanService
from pomotivato.services.task_service import TaskService

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


@router.delete("/{plan_date}/slots/{sector}", response_model=DayPlanDto)
async def remove_slot(
    plan_date: date, sector: int, session: DbSession, clock: ClockDep
) -> DayPlanDto:
    """Take one task off the day (spec 06 DF1): the week screen's ×."""
    service = DayPlanService(session)
    plan = await service.remove_slot(plan_date, sector, clock.now().date())
    return DayPlanDto.from_core(plan)


@router.delete("/{plan_date}", status_code=204)
async def clear_day_plan(plan_date: date, session: DbSession, clock: ClockDep) -> Response:
    """Forget the whole day (spec 06 DF1): the kanban calls it when the
    doing column empties, so ghost slots stop blocking card deletion."""
    service = DayPlanService(session)
    await service.clear(plan_date, clock.now().date())
    return Response(status_code=HTTPStatus.NO_CONTENT)


@router.post("/{plan_date}/add", response_model=AddResultDto)
async def add_task_to_day(
    plan_date: date,
    dto: DayPlanAddDto,
    session: DbSession,
    clock: ClockDep,
) -> AddResultDto:
    """Drag-to-plan primitive (spec 05 §3.8): append the task's chunk.

    200 even when the day was full — the outcome is in `skipped`, and an
    already-scheduled task is an idempotent no-op (GWT-A2).
    """
    service = DayPlanService(session)
    plan, outcome = await service.add(plan_date, dto.task_id, clock.now().date())
    return AddResultDto(
        plan=DayPlanDto.from_core(plan), added=list(outcome.added), skipped=list(outcome.skipped)
    )


@router.post("/{plan_date}/refresh-status", response_model=RefreshResultDto)
async def refresh_status(
    plan_date: date,
    dto: RefreshStatusDto,
    session: DbSession,
    clock: ClockDep,
) -> RefreshResultDto:
    """«Обновить статус» (spec 07 §6, A4/V25): carry the scope's today cards in.

    The whole move is all-or-nothing: a V25 overflow refuses the request and
    nothing moved (the transaction that would carry the writes never opens
    them — the limit check happens before the first status write). The date
    is path-supplied; past dates are refused like every other planning
    surface (⚑ Q4).
    """
    if plan_date < clock.now().date():
        msg = f"day plan for {plan_date.isoformat()} is in the past"
        raise ValidationError(msg)
    sprint_id, no_sprint = dto.scope()
    moved = await TaskService(session, clock).refresh_scope(
        plan_date, sprint_id=sprint_id, no_sprint=no_sprint
    )
    return RefreshResultDto(moved=moved)
