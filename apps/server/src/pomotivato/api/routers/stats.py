"""Stats router: GET /api/stats dashboard snapshot (spec 04 §4)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Query

from pomotivato.api.deps import ClockDep, DbSession
from pomotivato.api.schemas_stats import StatsDto
from pomotivato.services.stats_service import StatsService

router = APIRouter(prefix="/api", tags=["stats"])


@router.get("/stats", response_model=StatsDto)
async def get_stats(
    session: DbSession,
    clock: ClockDep,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
) -> StatsDto:
    """Dashboard snapshot; default period is the last 30 days (spec 04 §4)."""
    today = clock.now().date()
    start = date_from if date_from is not None else today - timedelta(days=29)
    end = date_to if date_to is not None else today
    payload = await StatsService(session).get(start, end, clock.now())
    return StatsDto(**payload)
