"""Repositories for session runtime tables + Q4 restart sweep (spec 02 §6).

Split from repository.py on purpose: the module passed the ~300-line smell
threshold (.hermes.md); resources (tasks/plans) and runtime (sessions/
segments/reviews/repetitions) are separate read-families anyway.
"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pomotivato.core.models import (
    RepetitionState,
    Review,
    Segment,
    SegmentStatus,
    Session,
    SessionState,
    repetition_state_from_dict,
    review_from_dict,
    segment_from_dict,
    session_from_dict,
    to_dict,
)
from pomotivato.infra.orm import RepetitionRow, ReviewRow, SegmentRow, SessionRow
from pomotivato.infra.repository import _iso


class SessionRepository:
    """Persistence for the sessions table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, session_model: Session) -> None:
        await self._session.merge(
            SessionRow(
                id=session_model.id,
                day_plan_id=session_model.day_plan_id,
                state=session_model.state.value,
                started_at=_iso(session_model.started_at),
                settings_json=json.dumps(to_dict(session_model.settings)),
                stop_reason=session_model.stop_reason,
            )
        )

    async def get(self, session_id: str) -> Session | None:
        row = await self._session.get(SessionRow, session_id)
        if row is None:
            return None
        return self._from_row(row)

    async def get_many_for_plan(self, day_plan_id: str) -> tuple[Session, ...]:
        """All sessions ever started on one day plan (summary reads them)."""
        stmt = select(SessionRow).where(SessionRow.day_plan_id == day_plan_id)
        rows = list(await self._session.scalars(stmt))
        return tuple(self._from_row(row) for row in rows)

    @staticmethod
    def _from_row(row: SessionRow) -> Session:
        return session_from_dict(
            {
                "id": row.id,
                "day_plan_id": row.day_plan_id,
                "state": row.state,
                "settings": json.loads(row.settings_json),
                "started_at": row.started_at,
                "stop_reason": row.stop_reason,
            }
        )


class SegmentRepository:
    """Persistence for segment rows; ids embed the FSM index (ordered)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, segment_id: str) -> Segment | None:
        row = await self._session.get(SegmentRow, segment_id)
        if row is None:
            return None
        return segment_from_dict(
            {
                "id": row.id,
                "session_id": row.session_id,
                "phase": row.phase,
                "planned_min": row.planned_min,
                "task_id": row.task_id,
                "started_at": row.started_at,
                "ended_at": row.ended_at,
                "status": row.status,
            }
        )

    async def upsert_many(self, segments: tuple[Segment, ...]) -> None:
        for segment in segments:
            await self._session.merge(
                SegmentRow(
                    id=segment.id,
                    session_id=segment.session_id,
                    task_id=segment.task_id,
                    phase=segment.phase.value,
                    planned_min=segment.planned_min,
                    started_at=_iso(segment.started_at),
                    ended_at=_iso(segment.ended_at),
                    status=segment.status.value if segment.status else None,
                )
            )

    async def get_many_for_session(self, session_id: str) -> tuple[Segment, ...]:
        stmt = (
            select(SegmentRow)
            .where(SegmentRow.session_id == session_id)
            .order_by(SegmentRow.started_at, SegmentRow.id)
        )
        rows = await self._session.scalars(stmt)
        return tuple(
            segment_from_dict(
                {
                    "id": row.id,
                    "session_id": row.session_id,
                    "phase": row.phase,
                    "planned_min": row.planned_min,
                    "task_id": row.task_id,
                    "started_at": row.started_at,
                    "ended_at": row.ended_at,
                    "status": row.status,
                }
            )
            for row in rows
        )

    async def exists(self, segment_id: str) -> bool:
        return await self._session.get(SegmentRow, segment_id) is not None


class ReviewRepository:
    """Persistence for the reviews table (one review per segment)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, review: Review) -> None:
        await self._session.merge(
            ReviewRow(
                segment_id=review.segment_id,
                score=review.score,
                comment=review.comment,
                recall_notes=review.recall_notes,
                reward=review.reward,
            )
        )

    async def get_many_for_session(self, session_id: str) -> tuple[Review, ...]:
        stmt = (
            select(ReviewRow)
            .join(SegmentRow, SegmentRow.id == ReviewRow.segment_id)
            .where(SegmentRow.session_id == session_id)
            .order_by(ReviewRow.segment_id)
        )
        rows = await self._session.scalars(stmt)
        return tuple(
            review_from_dict(
                {
                    "segment_id": row.segment_id,
                    "score": row.score,
                    "comment": row.comment,
                    "recall_notes": row.recall_notes,
                    "reward": row.reward,
                }
            )
            for row in rows
        )


class RepetitionRepository:
    """Spaced-repetition queue (one row per study task)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, task_id: str) -> RepetitionState | None:
        row = await self._session.get(RepetitionRow, task_id)
        if row is None:
            return None
        return repetition_state_from_dict(
            {
                "task_id": row.task_id,
                "interval_idx": row.interval_idx,
                "next_due": row.next_due,
            }
        )

    async def upsert(self, state: RepetitionState) -> None:
        data = to_dict(state)
        await self._session.merge(
            RepetitionRow(
                task_id=data["task_id"],
                interval_idx=data["interval_idx"],
                next_due=data["next_due"],
            )
        )


async def finalize_orphan_sessions(session: AsyncSession) -> int:
    """Q4 spec 02: live rows left by a restart become stopped/interrupted.

    Returns the number of swept sessions; the honest recovery (rehydrating
    the FSM from persisted segments) is part of E3 clock work.
    """
    stmt = select(SessionRow).where(
        SessionRow.state.in_([SessionState.RUNNING.value, SessionState.PAUSED.value])
    )
    rows = list(await session.scalars(stmt))
    for row in rows:
        row.state = SessionState.STOPPED.value
        row.stop_reason = "server_restart"
        open_stmt = select(SegmentRow).where(
            SegmentRow.session_id == row.id,
            SegmentRow.status.is_(None),
        )
        for segment in await session.scalars(open_stmt):
            segment.status = SegmentStatus.INTERRUPTED.value
    return len(rows)
