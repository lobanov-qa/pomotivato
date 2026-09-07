"""Week router: GET /api/week read-only browser (spec 04 §4.2).

The payload is discriminated by `kind` (StatusDto precedent): sections not
applicable to a day answer null, so clients branch on kind, never on key
presence (spec 04 §4.2).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Query

from pomotivato.api.deps import ClockDep, DbSession
from pomotivato.api.schemas_stats import WeekDto
from pomotivato.services.week_service import WeekService

router = APIRouter(prefix="/api", tags=["week"])


@router.get("/week", response_model=WeekDto)
async def get_week(
    session: DbSession,
    clock: ClockDep,
    start: Annotated[date | None, Query()] = None,
    days: Annotated[int, Query(ge=1, le=14)] = 7,
) -> WeekDto:
    """Seven-day window from Monday of the current week unless overridden."""
    today = clock.now().date()
    window_start = start if start is not None else today - timedelta(days=today.weekday())
    payload = await WeekService(session).get(window_start, days, today)
    return WeekDto(**payload)
