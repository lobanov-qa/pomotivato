"""Session timer FSM (spec 01 §4): pure, clock-driven, no HTTP/DB.

advance() is the single place time is applied: the E2 server and the
tests drive the exact same code path, so SSE tick events are derivatives
of this state machine, never a second implementation. The plan slots are
snapshotted at start() (spec v0.2 freeze): move_slot/recurrence changes
affect the next session only, protecting invariants I2/I3 of the live one.

Paused time never flows into WORK accounting: segments carry their own
paused_total and a completed work segment worked exactly planned_min.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import uuid4

from pomotivato.core.clock import Clock, as_utc
from pomotivato.core.errors import (
    DayPlanValidationError,
    InvalidReviewError,
    InvalidTransitionError,
)
from pomotivato.core.models import (
    DayPlan,
    Review,
    Segment,
    SegmentPhase,
    SegmentStatus,
    Session,
    SessionSettings,
    SessionState,
    Slot,
)
from pomotivato.core.validation import validate_review, validate_settings


@dataclass
class _Live:
    """Mutable in-flight segment; exposed via frozen Segment snapshots."""

    seg_id: str
    index: int
    phase: SegmentPhase
    planned_min: int
    task_id: str | None
    started_at: datetime
    ends_at: datetime
    paused_total: timedelta = field(default_factory=lambda: timedelta(0))
    status: SegmentStatus | None = None
    ended_at: datetime | None = None

    @property
    def is_open(self) -> bool:
        return self.ended_at is None

    @property
    def actual_worked(self) -> timedelta | None:
        if self.ended_at is None or self.phase is not SegmentPhase.WORK:
            return None
        return self.ended_at - self.started_at - self.paused_total


class SessionFSM:
    """Timer session lifecycle: IDLE -> RUNNING <-> PAUSED -> COMPLETED|STOPPED."""

    def __init__(
        self,
        clock: Clock,
        day_plan: DayPlan,
        settings: SessionSettings,
        session: Session | None = None,
    ) -> None:
        validate_settings(settings)
        if session is not None and session.state is not SessionState.IDLE:
            msg = f"cannot resume {session.state.value} session; DB rehydration lands in E2"
            raise InvalidTransitionError(msg)
        if not day_plan.slots:
            msg = "day plan must have at least one slot to start a session"
            raise DayPlanValidationError(msg)
        sectors = [slot.sector for slot in day_plan.slots]
        if len(set(sectors)) != len(sectors):
            msg = f"duplicate sectors in day plan: {sectors}"
            raise DayPlanValidationError(msg)
        self._clock = clock
        self._plan = day_plan
        self._settings = settings
        self._session_id = session.id if session is not None else f"session-{uuid4().hex[:12]}"
        self._slots: tuple[Slot, ...] = tuple(sorted(day_plan.slots, key=lambda s: s.sector))
        self._slot_cursor = 0
        self._segments: list[_Live] = []
        self._reviews: list[Review] = []
        self._state = SessionState.IDLE
        self._pause_started: datetime | None = None
        self._boundary_pause = False
        self._started_at: datetime | None = None
        self._stop_reason: str | None = None

    # ------------------------------------------------------------------ commands

    def start(self) -> None:
        """Open the session: snapshot plan order, begin the first WORK."""
        self._require_state(SessionState.IDLE, "start")
        self._state = SessionState.RUNNING
        self._started_at = self._now()
        self._open_segment(SegmentPhase.WORK, self._settings.work_min, self._started_at)

    def pause(self) -> None:
        """Freeze the running phase; paused wall time is excluded from work."""
        self._require_state(SessionState.RUNNING, "pause")
        self._pause_started = self._now()
        self._state = SessionState.PAUSED

    def resume(self) -> None:
        """Continue after a pause: a mid-phase pause shifts the deadline by the
        paused wall time; a boundary pause starts the next WORK now."""
        self._require_state(SessionState.PAUSED, "resume")
        now = self._now()
        if self._boundary_pause:
            self._boundary_pause = False
            self._state = SessionState.RUNNING
            self._open_segment(SegmentPhase.WORK, self._settings.work_min, now)
            return
        live = self._open_segment_or_none()
        assert live is not None  # only reachable via pause() which requires RUNNING
        if self._pause_started is not None:
            live.paused_total += now - self._pause_started
            live.ends_at = now + (live.ends_at - self._pause_started)
        self._pause_started = None
        self._state = SessionState.RUNNING

    def stop(self, reason: str = "user") -> None:
        """End the session early; the open segment becomes INTERRUPTED."""
        if self._state not in (SessionState.RUNNING, SessionState.PAUSED):
            msg = f"stop invalid in {self._state.value}"
            raise InvalidTransitionError(msg)
        live = self._open_segment_or_none()
        now = self._now()
        if live is not None and self._pause_started is not None:
            # fold the still-open pause span into the segment (I3)
            live.paused_total += now - self._pause_started
            self._pause_started = None
        if live is not None:
            self._close(live, now, SegmentStatus.INTERRUPTED)
        self._boundary_pause = False
        self._state = SessionState.STOPPED
        self._stop_reason = reason

    def skip_break(self) -> None:
        """Finish the open break early and start the next WORK now."""
        live = self._open_segment_or_none()
        if (
            self._state is not SessionState.RUNNING
            or live is None
            or live.phase is SegmentPhase.WORK
        ):
            msg = f"skip_break requires an open break, got {self._state.value}"
            raise InvalidTransitionError(msg)
        self._close(live, self._now(), SegmentStatus.COMPLETED)
        self._open_segment(SegmentPhase.WORK, self._settings.work_min, self._now())

    def advance(self) -> None:
        """Apply every phase deadline that has passed (catch-up cascade)."""
        if self._state is not SessionState.RUNNING:
            return
        now = self._now()
        while self._state is SessionState.RUNNING:
            live = self._open_segment_or_none()
            assert live is not None  # RUNNING always holds exactly one open segment
            if now < live.ends_at:
                break
            deadline = live.ends_at
            self._close(live, deadline, SegmentStatus.COMPLETED)
            if live.phase is SegmentPhase.WORK:
                if self._slot_cursor >= len(self._slots):
                    self._state = SessionState.COMPLETED
                    break
                if self._work_done() % self._settings.long_break_every == 0:
                    self._open_segment(
                        SegmentPhase.LONG_BREAK, self._settings.long_break_min, deadline
                    )
                else:
                    self._open_segment(SegmentPhase.BREAK, self._settings.break_min, deadline)
            elif self._settings.auto_start_next:
                self._open_segment(SegmentPhase.WORK, self._settings.work_min, deadline)
            else:
                self._boundary_pause = True
                self._state = SessionState.PAUSED

    def submit_review(self, segment_id: str, score: int, comment: str | None = None) -> Review:
        """Attach a review to a completed WORK segment; never blocks the FSM."""
        live = next((seg for seg in self._segments if seg.seg_id == segment_id), None)
        reviewable = (
            live is not None
            and live.phase is SegmentPhase.WORK
            and live.status is SegmentStatus.COMPLETED
        )
        if not reviewable:
            msg = f"segment {segment_id!r} is not a completed work block"
            raise InvalidReviewError(msg)
        if any(rev.segment_id == segment_id for rev in self._reviews):
            msg = f"segment {segment_id!r} already has a review"
            raise InvalidReviewError(msg)
        review = Review(segment_id=segment_id, score=score, comment=comment)
        validate_review(review)
        self._reviews.append(review)
        return review

    # ------------------------------------------------------------------ queries

    @property
    def state(self) -> SessionState:
        return self._state

    @property
    def phase(self) -> SegmentPhase | None:
        live = self._open_segment_or_none()
        return live.phase if live is not None else None

    @property
    def remaining(self) -> timedelta:
        if self._state is SessionState.RUNNING:
            live = self._open_segment_or_none()
            assert live is not None
            return max(timedelta(0), live.ends_at - self._now())
        if self._state is SessionState.PAUSED:
            if self._boundary_pause:
                return timedelta(minutes=self._settings.work_min)
            live = self._open_segment_or_none()
            assert live is not None and self._pause_started is not None
            # A pause taken while the server lags behind a passed deadline
            # shows 0, never negative (I5); resume keeps the overdue, so the
            # next advance closes the segment immediately — no time refund.
            return max(timedelta(0), live.ends_at - self._pause_started)
        if self._state is SessionState.IDLE:
            return timedelta(minutes=self._settings.work_min)
        return timedelta(0)

    @property
    def phase_ends_at(self) -> datetime | None:
        live = self._open_segment_or_none()
        return live.ends_at if live is not None else None

    @property
    def current_segment(self) -> Segment | None:
        live = self._open_segment_or_none()
        return self._snapshot(live) if live is not None else None

    @property
    def timeline(self) -> tuple[Segment, ...]:
        return tuple(self._snapshot(seg) for seg in self._segments)

    @property
    def reviews(self) -> tuple[Review, ...]:
        return tuple(self._reviews)

    @property
    def average_score(self) -> float | None:
        if not self._reviews:
            return None
        return sum(rev.score for rev in self._reviews) / len(self._reviews)

    @property
    def session(self) -> Session:
        return Session(
            id=self._session_id,
            day_plan_id=self._plan.id,
            state=self._state,
            settings=self._settings,
            started_at=self._started_at,
            stop_reason=self._stop_reason,
        )

    def snapshot(self) -> tuple[SessionState, SegmentPhase | None, tuple[Segment, ...]]:
        """Compact comparable state for no-op assertions (invariant I4)."""
        return (self._state, self.phase, self.timeline)

    def actual_worked(self, segment_id: str) -> timedelta | None:
        live = next((seg for seg in self._segments if seg.seg_id == segment_id), None)
        return live.actual_worked if live is not None else None

    # ------------------------------------------------------------------ internals

    def _require_state(self, expected: SessionState, cmd: str) -> None:
        if self._state is not expected:
            msg = f"{cmd} invalid in {self._state.value}"
            raise InvalidTransitionError(msg)

    def _now(self) -> datetime:
        return as_utc(self._clock.now())

    def _open_segment_or_none(self) -> _Live | None:
        if self._segments and self._segments[-1].is_open:
            return self._segments[-1]
        return None

    def _open_segment(self, phase: SegmentPhase, minutes: int, start_at: datetime) -> _Live:
        task_id: str | None = None
        if phase is SegmentPhase.WORK:
            task_id = self._slots[self._slot_cursor].task_id
            self._slot_cursor += 1
        live = _Live(
            seg_id=f"{self._session_id}-{len(self._segments)}",
            index=len(self._segments),
            phase=phase,
            planned_min=minutes,
            task_id=task_id,
            started_at=start_at,
            ends_at=start_at + timedelta(minutes=minutes),
        )
        self._segments.append(live)
        return live

    def _close(self, live: _Live, ended_at: datetime, status: SegmentStatus) -> None:
        live.ended_at = ended_at
        live.status = status

    def _work_done(self) -> int:
        return sum(
            1
            for seg in self._segments
            if seg.phase is SegmentPhase.WORK and seg.status is SegmentStatus.COMPLETED
        )

    def _snapshot(self, live: _Live) -> Segment:
        return Segment(
            id=live.seg_id,
            session_id=self._session_id,
            phase=live.phase,
            planned_min=live.planned_min,
            task_id=live.task_id,
            started_at=live.started_at,
            ended_at=live.ended_at,
            status=live.status,
        )
