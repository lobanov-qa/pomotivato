"""Stats snapshot assembly for GET /api/stats (spec 04 §4.1).

Reading glue only: loads rows once per request and hands them to the pure
projections in services/stats. The client never does arithmetic (E3 law).
Period scope: totals and heatmap follow from..to; streak/estimate/zombies
are whole-history by definition (spec 04 §3), so both sets ship in one
snapshot — a second endpoint would only duplicate the scans.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from pomotivato.core.errors import ValidationError
from pomotivato.core.models import Review, Segment, Task, TaskStatus
from pomotivato.infra.repository import TaskRepository
from pomotivato.infra.repository_sessions import (
    ReviewRepository,
    SegmentRepository,
    SessionRepository,
)
from pomotivato.services.blocks import WorkBlock, completed_work_blocks
from pomotivato.services.stats import (
    estimate_vs_fact,
    goal_depth,
    heatmap_rows,
    parent_progress,
    quadrant_stats,
    streaks,
    zombies,
)

DEFAULT_ZOMBIE_DAYS = 3
MAX_PERIOD_DAYS = 366  # spec 04 ⚑ Q6


class StatsService:
    """Load the persisted rows once and project the whole dashboard."""

    def __init__(self, session: AsyncSession) -> None:
        self._tasks = TaskRepository(session)
        self._sessions = SessionRepository(session)
        self._segments = SegmentRepository(session)
        self._reviews = ReviewRepository(session)

    async def get(self, start: date, end: date, now: datetime) -> dict[str, Any]:
        """Return the spec 04 §4.1 snapshot for [start, end]."""
        _validate_period(start, end)
        tasks, blocks, reviews = await self._load()
        period_blocks = tuple(b for b in blocks if start <= b.day <= end)
        period_ids = {b.segment_id for b in period_blocks}
        period_reviews = tuple(r for r in reviews if r.segment_id in period_ids)
        scores = [review.score for review in period_reviews]
        return {
            "period": {"from": start.isoformat(), "to": end.isoformat()},
            "totals": {
                "blocks_done": len(period_blocks),
                "focus_min": sum(b.minutes for b in period_blocks),
                "average_score": round(sum(scores) / len(scores), 2) if scores else None,
                "reviews_count": len(scores),
                "tasks_done": sum(1 for t in tasks if t.status is TaskStatus.DONE),
                "tasks_total": len(tasks),
            },
            "heatmap": heatmap_rows(blocks, start, end),
            "streak": streaks(blocks, today=now.date()),
            "estimate_vs_fact": estimate_vs_fact(tasks, blocks),
            "quadrants": quadrant_stats(tasks, blocks, reviews),
            "goal_depth": goal_depth(tasks),
            "parents": parent_progress(tasks),
            "zombies": zombies(tasks, blocks, now=now, threshold_days=DEFAULT_ZOMBIE_DAYS),
        }

    async def _load(
        self,
    ) -> tuple[tuple[Task, ...], tuple[WorkBlock, ...], tuple[Review, ...]]:
        tasks = await self._tasks.list_all()
        segments: list[Segment] = []
        reviews: list[Review] = []
        for model in await self._sessions.list_all():
            segments += list(await self._segments.get_many_for_session(model.id))
            reviews += list(await self._reviews.get_many_for_session(model.id))
        return tasks, completed_work_blocks(tuple(segments)), tuple(reviews)


def _validate_period(start: date, end: date) -> None:
    """Spec 04 §4: from<=to and at most MAX_PERIOD_DAYS apart."""
    if start > end:
        msg = f"period start {start} is after end {end}"
        raise ValidationError(msg)
    if (end - start).days > MAX_PERIOD_DAYS:
        msg = f"period {start}..{end} exceeds {MAX_PERIOD_DAYS} days"
        raise ValidationError(msg)
