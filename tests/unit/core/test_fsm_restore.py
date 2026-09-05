"""Core tests for SessionFSM.restore (spec 01 v0.3, spec 03 §6).

Restore must preserve I1–I5: deadlines recompute from persisted
(started, planned, paused_sec) — never from wall-time guesses — and the
frozen slot snapshot inside the session row (not any edited day plan)
keeps driving the next segments (GWT-M4).
"""

from __future__ import annotations

import contextlib
from dataclasses import replace
from datetime import timedelta

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from pomotivato.core.clock import FakeClock
from pomotivato.core.errors import InvalidTransitionError
from pomotivato.core.fsm import SessionFSM
from pomotivato.core.models import Review, Segment, SegmentPhase, Session, SessionState
from tests.factories.core_models import settings_factory

from .test_fsm_properties import FAST, shape_of
from .test_fsm_transitions import NINE, plan_with

STEP = st.tuples(
    st.integers(min_value=0, max_value=60),
    st.sampled_from(["pause", "resume", "skip_break", "advance"]),
)


def make_live(n_slots: int = 3) -> tuple[SessionFSM, FakeClock]:
    """A started machine on the shared FAST durations and a frozen clock."""
    clock = FakeClock(NINE)
    fsm = SessionFSM(clock, plan_with(n_slots), settings_factory(**FAST))
    fsm.start()
    return fsm, clock


def persisted(fsm: SessionFSM) -> tuple[Session, tuple[Segment, ...], tuple[Review, ...]]:
    """The exact triple the lifespan feeds to restore (what the DB stores)."""
    return (fsm.session, fsm.timeline, fsm.reviews)


@pytest.mark.unit
def test_restore_resumes_running_segment_at_same_deadline():
    fsm, clock = make_live()
    clock.advance(timedelta(minutes=3))

    restored = SessionFSM.restore(clock, *persisted(fsm))

    assert restored.state is SessionState.RUNNING
    assert restored.phase is SegmentPhase.WORK
    assert restored.remaining == timedelta(minutes=2)  # FAST work_min=5


@pytest.mark.unit
def test_restore_catches_overdue_phase_without_time_refund():
    fsm, clock = make_live()
    clock.advance(timedelta(minutes=7))  # 5-min work overdue by 2

    restored = SessionFSM.restore(clock, *persisted(fsm))
    restored.advance()  # one cascade: work AND the overdue break close on time

    timeline = restored.timeline
    assert timeline[0].ended_at == NINE + timedelta(minutes=5)  # original deadline
    assert timeline[1].phase is SegmentPhase.BREAK
    assert timeline[1].ended_at == NINE + timedelta(minutes=7)  # break burned too
    assert restored.phase is SegmentPhase.WORK  # next work starts at `now`
    assert restored.remaining == timedelta(minutes=5)  # nobody refunded, nobody cheated


@pytest.mark.unit
def test_restore_keeps_frozen_snapshot_after_plan_would_change():
    fsm, clock = make_live()
    original_slots = fsm.session.slots

    # Restore takes no day-plan argument at all: the snapshot in the row is
    # the only source, so a (hypothetically) edited plan cannot leak in.
    restored = SessionFSM.restore(clock, *persisted(fsm))

    assert restored.session.slots == original_slots


@pytest.mark.unit
def test_restore_frozen_pause_ignores_wall_time_during_downtime():
    fsm, clock = make_live()
    clock.advance(timedelta(minutes=2))
    fsm.pause()
    clock.advance(timedelta(minutes=30))  # downtime burns real time

    restored = SessionFSM.restore(clock, *persisted(fsm))

    assert restored.state is SessionState.PAUSED
    assert restored.remaining == timedelta(minutes=3)  # 5 - 2, pause froze the rest


@pytest.mark.unit
def test_restore_boundary_pause_resumes_by_opening_next_work():
    clock = FakeClock(NINE)
    fsm = SessionFSM(clock, plan_with(3), settings_factory(**FAST, auto_start_next=False))
    fsm.start()
    clock.advance(timedelta(minutes=7))  # work (5) AND break (2) deadlines pass
    fsm.advance()  # boundary pause: waiting on a segment edge, nothing open

    restored = SessionFSM.restore(clock, *persisted(fsm))
    restored.resume()

    assert restored.state is SessionState.RUNNING
    assert restored.phase is SegmentPhase.WORK
    assert restored.remaining == timedelta(minutes=5)


@pytest.mark.unit
def test_restore_refuses_legacy_row_without_snapshot():
    fsm, clock = make_live()
    legacy_session = replace(fsm.session, slots=None)

    with pytest.raises(InvalidTransitionError, match="predates snapshotting"):
        SessionFSM.restore(clock, legacy_session, fsm.timeline, fsm.reviews)


@pytest.mark.unit
def test_restore_refuses_finished_and_empty_rows():
    fsm, clock = make_live()
    stopped = replace(fsm.session, state=SessionState.STOPPED)
    with pytest.raises(InvalidTransitionError, match="only live"):
        SessionFSM.restore(clock, stopped, fsm.timeline, fsm.reviews)

    empty = replace(fsm.session, state=SessionState.RUNNING)
    with pytest.raises(InvalidTransitionError, match="predates snapshotting"):
        SessionFSM.restore(clock, empty, (), ())


@pytest.mark.unit
def test_restore_refuses_duplicate_sectors_in_snapshot():
    from pomotivato.core.errors import DayPlanValidationError
    from pomotivato.core.models import Slot

    fsm, clock = make_live()
    broken = replace(fsm.session, slots=(Slot(sector=1, task_id="a"), Slot(sector=1, task_id="b")))

    with pytest.raises(DayPlanValidationError, match="duplicate or empty sectors"):
        SessionFSM.restore(clock, broken, fsm.timeline, fsm.reviews)


@pytest.mark.unit
def test_restore_refuses_segment_without_start_stamp():
    fsm, _clock = make_live()
    clock = FakeClock(NINE)
    hole = replace(fsm.timeline[0], started_at=None)

    with pytest.raises(InvalidTransitionError, match="no started_at"):
        SessionFSM.restore(clock, fsm.session, (hole,), fsm.reviews)


@pytest.mark.unit
def test_restore_refuses_cursor_beyond_snapshot_slots():
    fsm, clock = make_live(n_slots=3)
    clock.advance(timedelta(minutes=7))  # work + break elapse -> second work opens
    fsm.advance()
    slots = fsm.session.slots
    assert slots is not None
    one_slot = replace(fsm.session, slots=slots[:1])

    with pytest.raises(InvalidTransitionError, match="more slots than it had"):
        SessionFSM.restore(clock, one_slot, fsm.timeline, fsm.reviews)


@pytest.mark.unit
def test_restore_refuses_paused_row_without_pause_anchor():
    fsm, clock = make_live()
    fsm.pause()
    lost = replace(fsm.session, pause_started_at=None)

    with pytest.raises(InvalidTransitionError, match="without pause_started_at"):
        SessionFSM.restore(clock, lost, fsm.timeline, fsm.reviews)


@pytest.mark.property
@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(steps=st.lists(STEP, min_size=1, max_size=8))
def test_restore_roundtrip_is_confluent_with_undisturbed_machine(steps):  # P10
    """persist -> restore replays the same machine: same remaining, same cascade."""
    fsm, clock = make_live(n_slots=4)
    for minutes, command in steps:
        clock.advance(timedelta(minutes=minutes))
        with contextlib.suppress(InvalidTransitionError):
            getattr(fsm, command)()
    if fsm.state not in (SessionState.RUNNING, SessionState.PAUSED):
        return  # the stream finished the machine: nothing to restore

    restored = SessionFSM.restore(clock, *persisted(fsm))
    assert restored.remaining == fsm.remaining

    # Both machines share the clock: an identical command tail must land
    # them on an identical structural timeline (ids excluded, see shape_of).
    for minutes, command in [(3, "advance"), (4, "pause"), (9, "advance")]:
        clock.advance(timedelta(minutes=minutes))
        for machine in (restored, fsm):
            with contextlib.suppress(InvalidTransitionError):
                getattr(machine, command)()

    assert shape_of(restored) == shape_of(fsm)
    assert restored.state is fsm.state
