"""ReviewService: FSM review delegation + spaced-repetition ladder (spec 02 §4/§5).

T16/T17 live in the core FSM (review never blocks, one per segment); this
service adds persistence and, for STUDY tasks, advances the review queue
via core `advance_repetition` (intervals owned by E1, not re-invented).
DF9–11 (spec 06): scoring a closed block is the day's verdict — the card
then moves itself. E4c rewrites the trigger as V22 (spec 07 §5.1): the
walk fires only when TODAY's blocks are exhausted — a two-sector card
that scored one block stays in work (the author's 24.09 bug (1)); the
destination follows the tick map (future -> planned, holes -> planned via
V31, everything worked -> done; shelf cards always close).
"""

from __future__ import annotations

from dataclasses import replace

from sqlalchemy.ext.asyncio import AsyncSession

from pomotivato.core.clock import Clock
from pomotivato.core.days import walk_after_day
from pomotivato.core.errors import InvalidReviewError
from pomotivato.core.models import RepetitionState, Review, TaskStatus, TaskType
from pomotivato.core.science import advance_repetition
from pomotivato.infra.errors import NotFoundError
from pomotivato.infra.repository import DayPlanRepository, TaskRepository
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
        self._day_plans = DayPlanRepository(session)

    async def submit(
        self,
        segment_id: str,
        score: int | None,
        comment: str | None = None,
        *,
        recall_notes: str | None = None,
        reward: str | None = None,
    ) -> Review:
        """V24/A39 (spec 07): score=None is the explicit skip verdict — the
        block closes, the card walks (_auto_move_after_review sees it the
        same), the repetition ladder still advances; only the mean stays
        untouched."""
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
        """V22 (spec 07 §5.1): the day-blocks come FIRST, then the tick map.

        DF9-11 made the score the day's verdict; E4c sharpened it into
        core.walk_after_day: a card whose plan-day holds two sectors and
        which scored one of them STAYS in «В работе» (author's 24.09 bug),
        and a card done for today returns to planned while future ticks
        remain, stays planned while any tick (even a past one) is unspent
        (V31), and only then closes. A shelf card (no sprint) closes once
        its day's blocks are gone (д). The score None (skip, A39) walks
        exactly like a real one.
        """
        if task_id is None:
            return
        task = await self._tasks.get(task_id)
        if task is None or task.status is not TaskStatus.DOING:
            return
        today = self._clock.now().date()
        plan = await self._day_plans.get_by_date(today)
        day_blocks = (
            sum(1 for slot in plan.slots if slot.task_id == task_id) if plan is not None else 0
        )
        done_today = (await self._segments.work_blocks_on(today)).get(task_id, 0)
        worked = (await self._segments.worked_days_by_task()).get(task_id, frozenset())
        nxt = walk_after_day(
            task, today, day_blocks=day_blocks, blocks_done_today=done_today, worked_days=worked
        )
        if nxt is not None:
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
