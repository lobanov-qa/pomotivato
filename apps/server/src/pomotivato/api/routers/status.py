"""Status + daily-summary routers (spec 03 §5).

/api/status is a stable external contract for scripts: flat JSON, additive
fields only. /api/summary reads a pure projection over persisted rows.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter

from pomotivato.api.deps import ClockDep, DbSession, RegistryDep
from pomotivato.api.schemas import DailySummaryDto, StatusDto
from pomotivato.services.daily_summary import DailySummaryService
from pomotivato.services.session_service import SessionService

status_router = APIRouter(prefix="/api", tags=["status"])
summary_router = APIRouter(prefix="/api/summary", tags=["summary"])


@status_router.get("/status", response_model=StatusDto)
async def get_status(
    session: DbSession,
    clock: ClockDep,
    registry: RegistryDep,
) -> StatusDto:
    """Report the live session for scripts (active session or nothing)."""
    now = clock.now()
    session_id = registry.latest_active()
    if session_id is None:
        return StatusDto(active=False, server_now=now.isoformat(), date=now.date().isoformat())
    view = await SessionService(session, clock, registry).get_view(session_id)
    return StatusDto(
        active=True,
        session_id=session_id,
        state=view.session.state.value,
        phase=view.phase,
        remaining_sec=view.remaining_sec,
        server_now=now.isoformat(),
        date=now.date().isoformat(),
    )


@summary_router.get("/{day}", response_model=DailySummaryDto)
async def get_summary(day: date, session: DbSession) -> DailySummaryDto:
    """Day totals for the /focus panel; unknown date answers zeros, not 404."""
    payload = await DailySummaryService(session).get(day)
    return DailySummaryDto(**payload)
