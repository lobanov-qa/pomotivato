"""ReviewService: FSM review delegation + spaced-repetition ladder (spec 02 §4/§5).

T16/T17 live in the core FSM (review never blocks, one per segment); this
service adds persistence and, for STUDY tasks, advances the review queue
via core `advance_repetition` (intervals owned by E1, not re-invented).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from pomotivato.core.clock import Clock
from pomotivato.core.errors import InvalidReviewError
from pomotivato.core.models import RepetitionState, Review, TaskType
from pomotivato.core.science import advance_repetition
from pomotivato.infra.errors import NotFoundError
from pomotivato.infra.repository import TaskRepository
from pomotivato.infra.repository_sessions import (
    RepetitionRepository,
    ReviewRepository,
    SegmentRepository,
)
from pomotivato.services.session_service import FsmRegistry


class ReviewService:
    """Submit reviews against active sessions and roll the study queue."""

    def __init__(
        self,
        session: AsyncSession,
        clock: Clock,
        registry: FsmRegistry,
    ) -> None:
        self._clock = clock
        self._registry = registry
        self._reviews = ReviewRepository(session)
        self._segments = SegmentRepository(session)
        self._repetitions = RepetitionRepository(session)
        self._tasks = TaskRepository(session)

    async def submit(self, segment_id: str, score: int, comment: str | None = None) -> Review:
        segment = await self._segments.get(segment_id)
        if segment is None:
            msg = f"segment {segment_id!r} not found"
            raise NotFoundError(msg)
        fsm = self._registry.get(segment.session_id)
        if fsm is None:
            msg = f"segment {segment_id!r} belongs to a finished session"
            raise InvalidReviewError(msg)
        review = fsm.submit_review(segment_id, score, comment)
        await self._reviews.upsert(review)
        await self._advance_repetition(segment.task_id)
        return review

    async def _advance_repetition(self, task_id: str | None) -> None:
        if task_id is None:
            return
        task = await self._tasks.get(task_id)
        if task is None or task.type is not TaskType.STUDY:
            return
        today = self._clock.now().date()
        current = await self._repetitions.get(task_id)
        state = current if current is not None else RepetitionState(task_id, 0, today)
        await self._repetitions.upsert(advance_repetition(state, today))
