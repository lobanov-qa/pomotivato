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
from datetime import date, datetime, time, timedelta, tzinfo
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
    SpecialBreak,
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
    break_label: str | None = None

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
        tz: tzinfo | None = None,
    ) -> None:
        validate_settings(settings)
        if session is not None and session.state is not SessionState.IDLE:
            msg = f"cannot resume {session.state.value} session; use SessionFSM.restore()"
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
        # Local wall zone for clock-anchored special breaks (⚑ Q2: the app
        # is single-machine; UTC stays the storage currency everywhere else).
        self._tz = tz if tz is not None else datetime.now().astimezone().tzinfo
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
        # Anchors at/before this instant are "missed while paused" and are
        # never applied retroactively (spec 05 GWT-B2: a pause through
        # lunch means the lunch already happened on the user's own time).
        self._last_resume: datetime | None = self._started_at
        # (local day, wall time) of every special break already applied to
        # the timeline, so the cascade cuts each anchor exactly once.
        self._consumed_anchors: set[tuple[date, time]] = set()

    # ------------------------------------------------------------------ commands

    def start(self) -> None:
        """Open the session: snapshot plan order, begin the first WORK.

        warm-up (spec 01 v0.4): the day's first segment lasts warmup_min
        (0 disables) — it is the ramp into flow, later blocks keep the
        normal work_min rhythm.
        """
        self._require_state(SessionState.IDLE, "start")
        self._state = SessionState.RUNNING
        self._started_at = self._now()
        self._last_resume = self._started_at
        self._open_segment(SegmentPhase.WORK, self._next_work_min(), self._started_at)

    def pause(self) -> None:
        """Freeze the running phase; paused wall time is excluded from work.

        strict mode (v0.4): while RUNNING with an open WORK the freeze is
        refused — a stop is always allowed, so the user is never trapped.
        """
        if self._settings.strict_mode:
            live = self._open_segment_or_none()
            if live is not None and live.phase is SegmentPhase.WORK:
                msg = "pause invalid in strict mode while working"
                raise InvalidTransitionError(msg)
        self._require_state(SessionState.RUNNING, "pause")
        self._pause_started = self._now()
        self._state = SessionState.PAUSED

    def resume(self) -> None:
        """Continue after a pause: a mid-phase pause shifts the deadline by the
        paused wall time; a boundary pause starts the next WORK now."""
        self._require_state(SessionState.PAUSED, "resume")
        now = self._now()
        # Paused-over anchors are consumed silently: they belong to the
        # wall time the user already spent on their own (GWT-B2).
        self._last_resume = now
        if self._boundary_pause:
            self._boundary_pause = False
            self._state = SessionState.RUNNING
            self._open_segment(SegmentPhase.WORK, self._next_work_min(), now)
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
        self._open_segment(SegmentPhase.WORK, self._next_work_min(), self._now())

    def advance(self) -> None:
        """Apply every phase deadline that has passed (catch-up cascade).

        Clock-anchored special breaks (spec 01 v0.4, spec 05 §3.3) are cut
        into this same loop: an anchor strictly inside the open segment
        closes it early (WORK -> INTERRUPTED, a plain break -> COMPLETED)
        and the special segment takes the rest of the ladder. Anchors at or
        before the last resume are never applied retroactively — time the
        user spent paused or before the session started is their own.
        """
        if self._state is not SessionState.RUNNING:
            return
        now = self._now()
        while self._state is SessionState.RUNNING:
            live = self._open_segment_or_none()
            assert live is not None  # RUNNING always holds exactly one open segment
            anchor = self._crossed_anchor(live.started_at, now)
            if anchor is not None and anchor < live.ends_at:
                status = (
                    SegmentStatus.INTERRUPTED
                    if live.phase is SegmentPhase.WORK
                    else SegmentStatus.COMPLETED
                )
                self._close(live, anchor, status)
                self._open_special(self._break_at(anchor), anchor)
                continue
            if now < live.ends_at:
                break
            deadline = live.ends_at
            self._close(live, deadline, SegmentStatus.COMPLETED)
            boundary = self._anchor_at(deadline)
            if boundary is not None:
                # Lunch landing exactly on a segment end takes the next slot
                # instead of the scheduled break (author's clock rules).
                self._open_special(boundary, deadline)
                continue
            if live.phase is SegmentPhase.WORK:
                if self._slot_cursor >= len(self._slots):
                    trailing = self._crossed_anchor(deadline, now)
                    if trailing is not None:
                        # GWT-B4: the ladder is over but lunch was crossed —
                        # it still happens, then the day completes.
                        self._open_special(self._break_at(trailing), trailing)
                        continue
                    self._state = SessionState.COMPLETED
                    break
                if self._work_done() % self._settings.long_break_every == 0:
                    self._open_segment(
                        SegmentPhase.LONG_BREAK, self._settings.long_break_min, deadline
                    )
                else:
                    self._open_segment(SegmentPhase.BREAK, self._settings.break_min, deadline)
            elif self._slot_cursor >= len(self._slots):
                # Only a trailing special (B4) can end the ladder; a plain
                # break never opens unless a WORK slot is still queued.
                self._state = SessionState.COMPLETED
                break
            elif self._settings.auto_start_next:
                self._open_segment(SegmentPhase.WORK, self._next_work_min(), deadline)
            else:
                self._boundary_pause = True
                self._state = SessionState.PAUSED

    def submit_review(
        self,
        segment_id: str,
        score: int,
        comment: str | None = None,
        *,
        recall_notes: str | None = None,
        reward: str | None = None,
    ) -> Review:
        """Attach a review to a completed WORK segment; never blocks the FSM.

        recall_notes/reward are E4b payload fields (spec 05 §3.7-3.8): the
        active-recall notes of a study block and the habit-loop reward.
        They arrive with the score; the ladder advance (E2) still triggers
        on the review itself.
        """
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
        review = Review(
            segment_id=segment_id,
            score=score,
            comment=comment,
            recall_notes=recall_notes,
            reward=reward,
        )
        validate_review(review)
        self._reviews.append(review)
        return review

    @classmethod
    def restore(
        cls,
        clock: Clock,
        session: Session,
        segments: tuple[Segment, ...],
        reviews: tuple[Review, ...],
        tz: tzinfo | None = None,
    ) -> SessionFSM:
        """Rehydrate a live FSM from persisted rows (spec 01 v0.3, spec 03 §6).

        The session carries its frozen slot snapshot, so a later day-plan
        edit cannot corrupt the running timer (GWT-M4). Deadlines recompute
        from the deadline invariant (started + planned + paused == ends),
        never from wall-time guesses; an overdue open segment is honest —
        the first advance() closes it at the original deadline, no refund.
        Raises InvalidTransitionError for rows that cannot be trusted
        (legacy pre-snapshot rows, gaps, cursor past the slots): the caller
        sweeps those to stopped/interrupted exactly like the old Q4 path.
        """
        validate_settings(session.settings)
        if session.state not in (SessionState.RUNNING, SessionState.PAUSED):
            msg = f"only live sessions can be restored, got {session.state.value}"
            raise InvalidTransitionError(msg)
        if session.slots is None or session.started_at is None or not segments:
            msg = f"session {session.id!r} predates snapshotting; cannot restore"
            raise InvalidTransitionError(msg)
        ordered = sorted(session.slots, key=lambda s: s.sector)
        sectors = [slot.sector for slot in ordered]
        if len(set(sectors)) != len(sectors) or not ordered:
            msg = f"duplicate or empty sectors in snapshot: {sectors}"
            raise DayPlanValidationError(msg)

        fsm = cls.__new__(cls)
        fsm._clock = clock
        started = session.started_at
        fsm._plan = DayPlan(id=session.day_plan_id, date=started.date(), slots=tuple(ordered))
        fsm._settings = session.settings
        fsm._tz = tz if tz is not None else datetime.now().astimezone().tzinfo
        fsm._session_id = session.id
        fsm._slots = tuple(ordered)
        fsm._segments = []
        for index, seg in enumerate(segments):
            if seg.started_at is None:
                msg = f"segment {seg.id!r} has no started_at; cannot restore"
                raise InvalidTransitionError(msg)
            deadline = seg.started_at + timedelta(minutes=seg.planned_min, seconds=seg.paused_sec)
            fsm._segments.append(
                _Live(
                    seg_id=seg.id,
                    index=index,
                    phase=seg.phase,
                    planned_min=seg.planned_min,
                    task_id=seg.task_id,
                    started_at=seg.started_at,
                    ends_at=deadline,
                    paused_total=timedelta(seconds=seg.paused_sec),
                    status=seg.status,
                    ended_at=seg.ended_at,
                    break_label=seg.break_label,
                )
            )
        fsm._reviews = list(reviews)
        fsm._started_at = session.started_at
        fsm._stop_reason = None
        # Special-break bookkeeping (spec 01 v0.4): anchors already present
        # in the timeline must not be re-cut after restore; anchors before
        # the session start belong to the user's own time.
        fsm._last_resume = session.started_at
        fsm._consumed_anchors = set()
        for seg in segments:
            if seg.phase is SegmentPhase.SPECIAL_BREAK and seg.started_at is not None:
                local = seg.started_at.astimezone(fsm._tz)
                fsm._consumed_anchors.add((local.date(), local.time()))

        open_live = fsm._open_segment_or_none()
        cursor = sum(seg.phase is SegmentPhase.WORK for seg in segments)
        if cursor > len(ordered):
            msg = f"session {session.id!r} consumed more slots than it had"
            raise InvalidTransitionError(msg)
        fsm._slot_cursor = cursor
        boundary = session.state is SessionState.PAUSED and open_live is None
        paused_no_anchor = (
            session.state is SessionState.PAUSED
            and not boundary
            and session.pause_started_at is None
        )
        if paused_no_anchor:
            msg = f"paused session {session.id!r} without pause_started_at"
            raise InvalidTransitionError(msg)
        fsm._state = session.state
        fsm._boundary_pause = boundary
        fsm._pause_started = None if boundary else session.pause_started_at
        return fsm

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
                return timedelta(minutes=self._next_work_min())
            live = self._open_segment_or_none()
            assert live is not None and self._pause_started is not None
            # A pause taken while the server lags behind a passed deadline
            # shows 0, never negative (I5); resume keeps the overdue, so the
            # next advance closes the segment immediately — no time refund.
            return max(timedelta(0), live.ends_at - self._pause_started)
        if self._state is SessionState.IDLE:
            return timedelta(minutes=self._next_work_min())
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
            slots=self._slots,
            pause_started_at=self._pause_started,
        )

    def snapshot(self) -> tuple[SessionState, SegmentPhase | None, tuple[Segment, ...]]:
        """Compact comparable state for no-op assertions (invariant I4)."""
        return (self._state, self.phase, self.timeline)

    def actual_worked(self, segment_id: str) -> timedelta | None:
        live = next((seg for seg in self._segments if seg.seg_id == segment_id), None)
        return live.actual_worked if live is not None else None

    # ------------------------------------------------------------------ internals

    def _next_work_min(self) -> int:
        """Warm-up is the day's FIRST work segment only (spec v0.4 §3.5)."""
        has_work = any(seg.phase is SegmentPhase.WORK for seg in self._segments)
        if not has_work and self._settings.warmup_min:
            return self._settings.warmup_min
        return self._settings.work_min

    def _anchor_instant(self, brk: SpecialBreak, within: datetime) -> datetime:
        """The break's wall instant on the local day containing `within`."""
        local = within.astimezone(self._tz)
        return datetime.combine(local.date(), brk.at, tzinfo=self._tz)

    def _crossed_anchor(self, after: datetime, now: datetime) -> datetime | None:
        """Earliest unconsumed anchor in (after, now] strictly after the last
        resume — the next special break the cascade must honour."""
        floor = self._last_resume
        for brk in sorted(self._settings.special_breaks, key=lambda b: b.at):
            instant = self._anchor_instant(brk, now)
            if instant <= after or instant > now:
                continue
            if floor is not None and instant <= floor:
                continue
            key = (instant.astimezone(self._tz).date(), brk.at)
            if key in self._consumed_anchors:
                continue
            return instant
        return None

    def _break_at(self, anchor: datetime) -> SpecialBreak:
        local = anchor.astimezone(self._tz)
        for brk in self._settings.special_breaks:
            if brk.at == local.time():
                return brk
        msg = f"anchor {anchor} matches no configured special break"  # defensive
        raise InvalidTransitionError(msg)

    def _anchor_at(self, when: datetime) -> SpecialBreak | None:
        """Unconsumed special break whose wall anchor equals `when` exactly."""
        if self._last_resume is not None and when <= self._last_resume:
            return None
        local = when.astimezone(self._tz)
        for brk in self._settings.special_breaks:
            if brk.at == local.time() and (local.date(), brk.at) not in self._consumed_anchors:
                return brk
        return None

    def _open_special(self, brk: SpecialBreak, start_at: datetime) -> _Live:
        local = start_at.astimezone(self._tz)
        self._consumed_anchors.add((local.date(), local.time()))
        live = self._open_segment(SegmentPhase.SPECIAL_BREAK, brk.duration_min, start_at)
        live.break_label = brk.label
        return live

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
            paused_sec=int(live.paused_total.total_seconds()),
            break_label=live.break_label,
        )
