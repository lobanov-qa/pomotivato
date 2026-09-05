"""Daily-summary projection for GET /api/summary/{date} (spec 03 §5).

`summarize` is a pure function over already-loaded rows — no rules are
invented here, only counts of what the FSM persisted; E4a dashboards reuse
the same projection. `DailySummaryService` is the reading glue.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from pomotivato.core.models import (
    DayPlan,
    Review,
    Segment,
    SegmentPhase,
    SegmentStatus,
)
from pomotivato.infra.repository import DayPlanRepository
from pomotivato.infra.repository_sessions import (
    ReviewRepository,
    SegmentRepository,
    SessionRepository,
)


def summarize(
    day: date,
    plan: DayPlan | None,
    segments: tuple[Segment, ...],
    reviews: tuple[Review, ...],
) -> dict[str, Any]:
    """Project one day's rows into the summary payload.

    Only COMPLETED work segments count (breaks never do); a day without a
    plan reports zero planned instead of an error.
    """
    done_work = [
        segment
        for segment in segments
        if segment.phase is SegmentPhase.WORK and segment.status is SegmentStatus.COMPLETED
    ]
    focus_min = round(
        sum(
            (segment.ended_at - segment.started_at).total_seconds()
            for segment in done_work
            if segment.ended_at is not None and segment.started_at is not None
        )
        / 60
    )
    scores = [review.score for review in reviews]
    return {
        "date": day.isoformat(),
        "blocks_done": len(done_work),
        "blocks_planned": len(plan.slots) if plan is not None else 0,
        "focus_min": focus_min,
        "average_score": round(sum(scores) / len(scores), 2) if scores else None,
        "reviews_count": len(scores),
        "tasks_done": len({segment.task_id for segment in done_work if segment.task_id}),
    }


class DailySummaryService:
    """Load the rows behind one date and hand them to the pure projection."""

    def __init__(self, session: AsyncSession) -> None:
        self._plans = DayPlanRepository(session)
        self._sessions = SessionRepository(session)
        self._segments = SegmentRepository(session)
        self._reviews = ReviewRepository(session)

    async def get(self, day: date) -> dict[str, Any]:
        plan = await self._plans.get_by_date(day)
        segments: list[Segment] = []
        reviews: list[Review] = []
        if plan is not None:
            for session_model in await self._sessions.get_many_for_plan(plan.id):
                segments += list(await self._segments.get_many_for_session(session_model.id))
                reviews += list(await self._reviews.get_many_for_session(session_model.id))
        return summarize(day, plan, tuple(segments), tuple(reviews))
