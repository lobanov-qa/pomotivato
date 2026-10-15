"""Sessions router: FSM lifecycle over HTTP (spec 02 §5).

Commands are one-liner delegations to SessionService; catch-up happens
on every read, so the dial stays honest even if nobody polls for a while.
"""

from __future__ import annotations

from fastapi import APIRouter

from pomotivato.api.deps import ClockDep, DbSession, RegistryDep
from pomotivato.api.schemas import ReorderSectorDto, SessionCreateDto, SessionDto
from pomotivato.infra.errors import NotFoundError
from pomotivato.infra.repository import DayPlanRepository
from pomotivato.services.session_service import SessionService
from pomotivato.services.settings_service import SettingsService

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _service(session: DbSession, clock: ClockDep, registry: RegistryDep) -> SessionService:
    return SessionService(session, clock, registry)


@router.post("", status_code=201, response_model=SessionDto)
async def create_session(
    dto: SessionCreateDto,
    session: DbSession,
    clock: ClockDep,
    registry: RegistryDep,
) -> SessionDto:
    plan = await DayPlanRepository(session).get(dto.day_plan_id)
    if plan is None:
        msg = f"day plan {dto.day_plan_id!r} not found"
        raise NotFoundError(msg)
    if dto.settings is not None:
        settings = dto.settings.to_core()
    else:
        settings = await SettingsService(session).get_session_settings()
    view = await _service(session, clock, registry).start(
        plan, settings, sprint_id=dto.sprint_id, no_sprint=dto.no_sprint
    )
    return SessionDto.from_view(view)


@router.get("/{session_id}", response_model=SessionDto)
async def get_session_state(
    session_id: str,
    session: DbSession,
    clock: ClockDep,
    registry: RegistryDep,
) -> SessionDto:
    view = await _service(session, clock, registry).get_view(session_id)
    return SessionDto.from_view(view)


@router.post("/{session_id}/pause", response_model=SessionDto)
async def pause_session(
    session_id: str, session: DbSession, clock: ClockDep, registry: RegistryDep
) -> SessionDto:
    view = await _service(session, clock, registry).command(session_id, "pause")
    return SessionDto.from_view(view)


@router.post("/{session_id}/resume", response_model=SessionDto)
async def resume_session(
    session_id: str, session: DbSession, clock: ClockDep, registry: RegistryDep
) -> SessionDto:
    view = await _service(session, clock, registry).command(session_id, "resume")
    return SessionDto.from_view(view)


@router.post("/{session_id}/stop", response_model=SessionDto)
async def stop_session(
    session_id: str, session: DbSession, clock: ClockDep, registry: RegistryDep
) -> SessionDto:
    view = await _service(session, clock, registry).command(session_id, "stop")
    return SessionDto.from_view(view)


@router.post("/{session_id}/skip-break", response_model=SessionDto)
async def skip_break_session(
    session_id: str, session: DbSession, clock: ClockDep, registry: RegistryDep
) -> SessionDto:
    view = await _service(session, clock, registry).command(session_id, "skip_break")
    return SessionDto.from_view(view)


@router.post("/{session_id}/reorder", response_model=SessionDto)
async def reorder_sector(
    session_id: str,
    dto: ReorderSectorDto,
    session: DbSession,
    clock: ClockDep,
    registry: RegistryDep,
) -> SessionDto:
    """DF27 (author 15.10): the legend arrows reorder the UNPLAYED tail of
    a live session. The FSM enforces the law (played sectors never move);
    the answer is the fresh view, so the dial paints the new order at once."""
    service = _service(session, clock, registry)
    view = await service.reorder(session_id, dto.sector, dto.direction)
    return SessionDto.from_view(view)
