"""SessionService: in-process FSM registry over persistent rows (spec 02 §4/§6).

The timer authority is the core SessionFSM (E1). One registry lives per
server process (app.state); every command mirrors the FSM into SQLite, so
GETs of finished sessions read the DB, and a restart sweeps orphan live
rows to stopped/interrupted (Q4). Rehydrating a running FSM is E3 work.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from pomotivato.core.clock import Clock
from pomotivato.core.fsm import SessionFSM
from pomotivato.core.models import (
    DayPlan,
    Review,
    Segment,
    Session,
    SessionSettings,
    SessionState,
)
from pomotivato.infra.errors import ConflictError, NotFoundError
from pomotivato.infra.repository_sessions import (
    ReviewRepository,
    SegmentRepository,
    SessionRepository,
)


@dataclass
class SessionView:
    """Everything the dial screen needs in one read."""

    session: Session
    phase: str | None
    remaining_sec: int
    ends_at: datetime | None
    timeline: tuple[Segment, ...]
    reviews: tuple[Review, ...]
    average_score: float | None


class FsmRegistry:
    """Live SessionFSM objects keyed by id (one per server process)."""

    def __init__(self) -> None:
        self._by_id: dict[str, SessionFSM] = {}

    def put(self, fsm: SessionFSM) -> None:
        self._by_id[fsm.session.id] = fsm

    def get(self, session_id: str) -> SessionFSM | None:
        return self._by_id.get(session_id)

    def drop(self, session_id: str) -> None:
        self._by_id.pop(session_id, None)

    def latest_active(self) -> str | None:
        """Most recently started still-live session id (spec 03 /api/status)."""
        for fsm in reversed(list(self._by_id.values())):
            if fsm.state in (SessionState.RUNNING, SessionState.PAUSED):
                return fsm.session.id
        return None


class SessionService:
    """Create sessions, execute FSM commands, mirror to the database."""

    def __init__(
        self,
        session: AsyncSession,
        clock: Clock,
        registry: FsmRegistry,
    ) -> None:
        self._session = session
        self._clock = clock
        self._registry = registry
        self._sessions = SessionRepository(session)
        self._segments = SegmentRepository(session)
        self._reviews = ReviewRepository(session)

    async def start(self, plan: DayPlan, settings: SessionSettings) -> SessionView:
        fsm = SessionFSM(clock=self._clock, day_plan=plan, settings=settings)
        fsm.start()
        self._registry.put(fsm)
        await self._persist(fsm)
        return self._view(fsm)

    async def command(self, session_id: str, verb: str) -> SessionView:
        fsm = await self._live_fsm(session_id)
        match verb:
            case "pause":
                fsm.pause()
            case "resume":
                fsm.resume()
            case "stop":
                fsm.stop()
                self._registry.drop(session_id)
            case "skip_break":
                fsm.skip_break()
            case "advance":
                fsm.advance()
            case _:
                msg = f"unknown session verb {verb!r}"
                raise ConflictError(msg)
        await self._persist(fsm)
        return self._view(fsm)

    async def get_view(self, session_id: str) -> SessionView:
        live = self._registry.get(session_id)
        if live is not None:
            # Catch-up first: deadlines crossed while nobody was watching.
            live.advance()
            view = self._view(live)
            await self._persist(live)
            return view
        stored = await self._sessions.get(session_id)
        if stored is None:
            msg = f"session {session_id!r} not found"
            raise NotFoundError(msg)
        timeline = await self._segments.get_many_for_session(session_id)
        reviews = await self._reviews.get_many_for_session(session_id)
        average = sum(review.score for review in reviews) / len(reviews) if reviews else None
        return SessionView(
            session=stored,
            phase=None,
            remaining_sec=0,
            ends_at=None,
            timeline=timeline,
            reviews=reviews,
            average_score=average,
        )

    async def _live_fsm(self, session_id: str) -> SessionFSM:
        fsm = self._registry.get(session_id)
        if fsm is not None:
            return fsm
        # Not in the registry: existing-but-finished rows are 409 conflicts
        # (restart sweep included), unknown ids are 404.
        if await self._sessions.get(session_id) is not None:
            msg = f"session {session_id!r} is not active"
            raise ConflictError(msg)
        msg = f"session {session_id!r} not found"
        raise NotFoundError(msg)

    async def _persist(self, fsm: SessionFSM) -> None:
        await self._sessions.upsert(fsm.session)
        await self._segments.upsert_many(fsm.timeline)
        await self._session.flush()

    def _view(self, fsm: SessionFSM) -> SessionView:
        remaining: timedelta = fsm.remaining
        return SessionView(
            session=fsm.session,
            phase=fsm.phase.value if fsm.phase else None,
            remaining_sec=int(remaining.total_seconds()),
            ends_at=fsm.phase_ends_at,
            timeline=fsm.timeline,
            reviews=fsm.reviews,
            average_score=fsm.average_score,
        )
