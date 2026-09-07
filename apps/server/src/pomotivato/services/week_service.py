"""Week-browser assembly for GET /api/week (spec 04 §4.2).

Reading glue over the pure week projection: plans/slots for the window,
completed blocks with their reviews, and the task list feeding recurrence
materialization. No writes — planning onto this screen is E4b (ADR-0003).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from pomotivato.core.errors import ValidationError
from pomotivato.core.models import Slot
from pomotivato.infra.repository import DayPlanRepository, TaskRepository
from pomotivato.infra.repository_sessions import (
    ReviewRepository,
    SegmentRepository,
    SessionRepository,
)
from pomotivato.services.blocks import WorkBlock, completed_work_blocks
from pomotivato.services.week_view import week_projection

MAX_WINDOW_DAYS = 14  # spec 04 §4: a fortnight is the honest browse limit


class WeekService:
    """Load one window's rows and project the week-view payload."""

    def __init__(self, session: AsyncSession) -> None:
        self._tasks = TaskRepository(session)
        self._plans = DayPlanRepository(session)
        self._sessions = SessionRepository(session)
        self._segments = SegmentRepository(session)
        self._reviews = ReviewRepository(session)

    async def get(self, start: date, days: int, today: date) -> dict[str, Any]:
        """Window [start, start+days) of the read-only browser."""
        _validate_window(days)
        plans: dict[date, tuple[Slot, ...]] = {}
        for offset in range(days):
            plan = await self._plans.get_by_date(start + timedelta(days=offset))
            if plan is not None:
                plans[plan.date] = plan.slots
        blocks, scores = await self._blocks_and_scores(start, days)
        tasks = await self._tasks.list_all()
        return week_projection(
            start=start,
            days=days,
            today=today,
            plans=plans,
            blocks=blocks,
            scores=scores,
            tasks=tasks,
        )

    async def _blocks_and_scores(
        self, start: date, days: int
    ) -> tuple[tuple[WorkBlock, ...], dict[str, int]]:
        end = start + timedelta(days=days - 1)
        segments = []
        scores: dict[str, int] = {}
        for model in await self._sessions.list_all():
            for segment in await self._segments.get_many_for_session(model.id):
                if segment.started_at is not None and start <= segment.started_at.date() <= end:
                    segments.append(segment)
            for review in await self._reviews.get_many_for_session(model.id):
                scores[review.segment_id] = review.score
        return completed_work_blocks(tuple(segments)), scores


def _validate_window(days: int) -> None:
    if not 1 <= days <= MAX_WINDOW_DAYS:
        msg = f"days must be 1..{MAX_WINDOW_DAYS}, got {days}"
        raise ValidationError(msg)
