"""ReviewService: FSM review delegation + spaced-repetition ladder (spec 02 §4/§5).

T16/T17 live in the core FSM (review never blocks, one per segment); this
service adds persistence and, for STUDY tasks, advances the review queue
via core `advance_repetition` (intervals owned by E1, not re-invented).
DF9–11 (spec 06): scoring a closed block is the day's verdict — the card
then moves itself (planned with progress left, or done when not).
"""

from __future__ import annotations

from dataclasses import replace

from sqlalchemy.ext.asyncio import AsyncSession

from pomotivato.core.clock import Clock
from pomotivato.core.errors import InvalidReviewError
from pomotivato.core.models import RepetitionState, Review, TaskStatus, TaskType
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

    async def submit(
        self,
        segment_id: str,
        score: int,
        comment: str | None = None,
        *,
        recall_notes: str | None = None,
        reward: str | None = None,
    ) -> Review:
        segment = await self._segments.get(segment_id)
        if segment is None:
            msg = f"segment {segment_id!r} not found"
            raise NotFoundError(msg)
        fsm = self._registry.get(segment.session_id)
        if fsm is None:
            msg = f"segment {segment_id!r} belongs to a finished session"
            raise InvalidReviewError(msg)
        review = fsm.submit_review(
            segment_id, score, comment, recall_notes=recall_notes, reward=reward
        )
        await self._reviews.upsert(review)
        await self._advance_repetition(segment.task_id)
        await self._auto_move_after_review(segment.task_id)
        return review

    async def _auto_move_after_review(self, task_id: str | None) -> None:
        """DF9–11 (spec 06): the score is the day's verdict, no button for it.

        A scored-off timer card with future repeat days returns to PLANNED
        (its "2 of 5" progress is the past segments themselves); a single
        run or the last tick closes as DONE. doing->planned and doing->done
        are both legal V7 transitions — the machine already allowed what
        the author asked for; only the trigger was missing. Errands (no
        timer) never run the FSM, so they never land here.
        """
        if task_id is None:
            return
        task = await self._tasks.get(task_id)
        if task is None or task.status is not TaskStatus.DOING:
            return
        today = self._clock.now().date()
        nxt = TaskStatus.DONE if not task.repeat_days_ahead(today) else TaskStatus.PLANNED
        await self._tasks.put(replace(task, status=nxt))

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
