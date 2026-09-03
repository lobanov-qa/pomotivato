"""Property-based tests for the FSM (spec 01 §8, P1/P2/P3/P7).

A random-but-reproducible command stream drives the machine; invariants
must hold on the resulting timeline and rejected commands must be no-ops.
Time only moves through FakeClock — full days are played in zero seconds.
"""

from __future__ import annotations

import contextlib
from datetime import timedelta

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from pomotivato.core.clock import FakeClock
from pomotivato.core.errors import InvalidTransitionError
from pomotivato.core.fsm import SessionFSM
from pomotivato.core.models import Segment, SegmentPhase, SegmentStatus, SessionState
from tests.factories.core_models import settings_factory

from .test_fsm_transitions import NINE, plan_with

pytestmark = pytest.mark.property

# Small durations keep 12-step streams crossing many phase boundaries.
FAST = {"work_min": 5, "break_min": 2, "long_break_min": 8, "long_break_every": 3}
COMMAND = st.sampled_from(["pause", "resume", "stop", "skip_break", "advance"])
STEP = st.tuples(st.integers(min_value=0, max_value=90), COMMAND)


def drive(steps: list[tuple[int, str]]) -> SessionFSM:
    """Start a 4-slot session and apply a command stream, ignoring refusals."""
    clock = FakeClock(NINE)
    fsm = SessionFSM(clock, plan_with(4), settings_factory(**FAST))
    fsm.start()
    for minutes, command in steps:
        clock.advance(timedelta(minutes=minutes))
        with contextlib.suppress(InvalidTransitionError):
            getattr(fsm, command)()  # refusal on a random stream is expected (P7)
    return fsm


def closed_work_segments(fsm: SessionFSM) -> list[Segment]:
    return [
        seg
        for seg in fsm.timeline
        if seg.phase is SegmentPhase.WORK and seg.status is SegmentStatus.COMPLETED
    ]


def shape_of(fsm: SessionFSM) -> list[tuple[object, int, object, object, object]]:
    """Structural timeline view: everything but per-session random ids."""
    return [(s.phase, s.planned_min, s.started_at, s.ended_at, s.status) for s in fsm.timeline]


@settings(max_examples=80, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(steps=st.lists(STEP, max_size=12))
def test_segments_are_ordered_and_never_overlap(steps):  # P1 / I2
    fsm = drive(steps)
    timeline = fsm.timeline

    for prev, nxt in zip(timeline, timeline[1:], strict=False):
        assert prev.ended_at is not None and nxt.started_at is not None
        assert nxt.started_at >= prev.ended_at


@settings(max_examples=80, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(steps=st.lists(STEP, max_size=12))
def test_remaining_never_negative(steps):  # I5
    fsm = drive(steps)

    assert fsm.remaining >= timedelta(0)


@settings(max_examples=80, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(steps=st.lists(STEP, max_size=12))
def test_work_segments_never_log_more_than_planned(steps):  # P2 / I3
    fsm = drive(steps)

    for seg in closed_work_segments(fsm):
        assert fsm.actual_worked(seg.id) == timedelta(minutes=seg.planned_min)


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(deltas=st.lists(st.integers(min_value=0, max_value=90), min_size=2, max_size=8))
def test_single_catchup_advance_equals_stepwise_drive(deltas):  # P3 confluence
    # Advance-only streams are confluent: catch-up closes segments at their
    # own deadlines, so one big advance and many small ones give one timeline.
    big = drive([(sum(deltas), "advance")])
    stepwise = drive([(d, "advance") for d in deltas])

    assert shape_of(big) == shape_of(stepwise)
    assert big.state == stepwise.state


@settings(max_examples=80, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(steps=st.lists(STEP, max_size=8), cmd=COMMAND)
def test_rejected_commands_are_noops(steps, cmd):  # P7 / I4
    fsm = drive(steps)
    assume(fsm.state not in (SessionState.STOPPED, SessionState.COMPLETED))
    before = fsm.snapshot()

    try:
        getattr(fsm, cmd)()
    except InvalidTransitionError:
        assert fsm.snapshot() == before
