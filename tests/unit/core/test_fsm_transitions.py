"""Unit tests for SessionFSM transitions (spec 01 §4.3, T1..T17)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from pomotivato.core.clock import FakeClock
from pomotivato.core.errors import (
    InvalidReviewError,
)
from pomotivato.core.fsm import SessionFSM
from pomotivato.core.models import (
    DayPlan,
    SegmentPhase,
    SegmentStatus,
    SessionState,
    Slot,
)
from tests.factories.core_models import settings_factory, task_factory

NINE = datetime(2026, 9, 3, 9, 0, tzinfo=UTC)


def plan_with(n_slots: int) -> DayPlan:
    tasks = [task_factory() for _ in range(n_slots)]
    slots = tuple(Slot(sector=i + 1, task_id=t.id) for i, t in enumerate(tasks))
    return DayPlan(id="plan-under-test", date=date(2026, 9, 3), slots=slots)


def make_fsm(
    n_slots: int = 3, *, clock_at: datetime = NINE, **settings_kw: object
) -> tuple[SessionFSM, FakeClock]:
    clock = FakeClock(clock_at)
    fsm = SessionFSM(clock, plan_with(n_slots), settings_factory(**settings_kw))
    return fsm, clock


def advance_min(clock: FakeClock, minutes: int) -> None:
    clock.advance(timedelta(minutes=minutes))


# mypy narrows fsm.state/fsm.phase after an identity assert and does not
# invalidate that across mutating calls; these helpers give each check a
# fresh declared type.
def state_of(fsm: SessionFSM) -> SessionState:
    return fsm.state


def phase_of(fsm: SessionFSM) -> SegmentPhase | None:
    return fsm.phase


# ---------------------------------------------------------------- happy paths


@pytest.mark.unit
def test_start_opens_first_work_when_idle():  # T1
    fsm, clock = make_fsm()

    fsm.start()

    assert fsm.state is SessionState.RUNNING
    assert fsm.phase is SegmentPhase.WORK
    seg = fsm.current_segment
    assert seg is not None and seg.started_at == NINE
    assert fsm.phase_ends_at == NINE.replace(hour=9, minute=25)
    assert fsm.remaining.total_seconds() == 25 * 60


@pytest.mark.unit
def test_pause_freezes_remaining_when_running():  # T2
    fsm, clock = make_fsm()
    fsm.start()
    advance_min(clock, 10)

    fsm.pause()

    assert fsm.state is SessionState.PAUSED
    assert fsm.phase is SegmentPhase.WORK
    assert fsm.remaining.total_seconds() == 15 * 60


@pytest.mark.unit
def test_resume_shifts_deadline_by_paused_time_when_resumed():  # T3
    fsm, clock = make_fsm()
    fsm.start()
    advance_min(clock, 10)
    fsm.pause()
    advance_min(clock, 5)

    fsm.resume()

    assert fsm.state is SessionState.RUNNING
    assert fsm.remaining.total_seconds() == 15 * 60
    assert fsm.phase_ends_at == NINE.replace(hour=9, minute=30)  # 09:25 deadline + 5 paused


@pytest.mark.unit
def test_work_becomes_break_when_deadline_passes():  # T4
    fsm, clock = make_fsm()
    fsm.start()
    advance_min(clock, 25)
    fsm.advance()

    first, second = fsm.timeline[0], fsm.timeline[1]
    assert first.status is SegmentStatus.COMPLETED
    assert first.ended_at == NINE.replace(hour=9, minute=25)
    assert second.phase is SegmentPhase.BREAK
    assert second.started_at == NINE.replace(hour=9, minute=25)
    assert fsm.phase_ends_at == NINE.replace(hour=9, minute=30)


@pytest.mark.unit
def test_fourth_work_opens_long_break_when_cadence_reached():  # T5
    fsm, clock = make_fsm(n_slots=5)
    fsm.start()
    for _ in range(3):  # three full work+break cycles
        advance_min(clock, 25)
        fsm.advance()
        advance_min(clock, 5)
        fsm.advance()
    advance_min(clock, 25)  # the 4th work reaches its deadline

    fsm.advance()

    assert fsm.phase is SegmentPhase.LONG_BREAK
    assert fsm.remaining.total_seconds() == 15 * 60


@pytest.mark.unit
def test_break_flows_into_next_work_when_auto_start():  # T6
    fsm, clock = make_fsm()
    fsm.start()
    advance_min(clock, 25)
    fsm.advance()

    advance_min(clock, 5)
    fsm.advance()

    assert fsm.state is SessionState.RUNNING
    assert fsm.phase is SegmentPhase.WORK
    assert fsm.current_segment is not None
    assert fsm.current_segment.started_at == NINE.replace(hour=9, minute=30)


@pytest.mark.unit
def test_break_ends_in_boundary_pause_when_auto_start_off():  # T7
    fsm, clock = make_fsm(auto_start_next=False)
    fsm.start()
    advance_min(clock, 25)
    fsm.advance()

    advance_min(clock, 5)
    fsm.advance()

    assert state_of(fsm) is SessionState.PAUSED
    assert phase_of(fsm) is None
    assert fsm.remaining.total_seconds() == 25 * 60
    advance_min(clock, 10)
    assert fsm.remaining.total_seconds() == 25 * 60  # still frozen while paused

    fsm.resume()

    assert state_of(fsm) is SessionState.RUNNING
    assert phase_of(fsm) is SegmentPhase.WORK
    assert fsm.current_segment is not None
    assert fsm.current_segment.started_at == NINE.replace(hour=9, minute=40)


@pytest.mark.unit
def test_last_work_completes_session_without_trailing_break():  # T8
    fsm, clock = make_fsm(n_slots=1)
    fsm.start()
    advance_min(clock, 25)

    fsm.advance()

    assert fsm.state is SessionState.COMPLETED
    assert fsm.timeline[0].status is SegmentStatus.COMPLETED
    assert len(fsm.timeline) == 1


@pytest.mark.unit
def test_stop_interrupts_open_work_when_running():  # T9
    fsm, clock = make_fsm()
    fsm.start()
    advance_min(clock, 10)

    fsm.stop("user")

    assert fsm.state is SessionState.STOPPED
    assert fsm.session.stop_reason == "user"
    seg = fsm.timeline[0]
    assert seg.status is SegmentStatus.INTERRUPTED
    assert seg.ended_at == NINE.replace(hour=9, minute=10)


@pytest.mark.unit
def test_stop_from_pause_excludes_paused_time():  # T10
    fsm, clock = make_fsm()
    fsm.start()
    advance_min(clock, 10)
    fsm.pause()
    advance_min(clock, 30)

    fsm.stop()

    seg = fsm.timeline[0]
    assert seg.status is SegmentStatus.INTERRUPTED
    assert fsm.actual_worked(seg.id) == timedelta(minutes=10)


@pytest.mark.unit
def test_pause_spans_work_boundary_without_phase_change():  # T11
    fsm, clock = make_fsm()
    fsm.start()
    advance_min(clock, 24)
    fsm.pause()

    advance_min(clock, 16)
    fsm.advance()  # server "wakes up" while paused

    assert fsm.state is SessionState.PAUSED
    assert fsm.phase is SegmentPhase.WORK
    assert fsm.remaining.total_seconds() == 60
    assert fsm.timeline[0].status is None


@pytest.mark.unit
def test_pause_after_deadline_passed_shows_zero_not_negative():
    # Found by Hypothesis (I5 property run): pause while the server lags
    # behind the deadline must never report negative remaining.
    fsm, clock = make_fsm()
    fsm.start()
    advance_min(clock, 30)  # work deadline 09:25 passed, advance() not called

    fsm.pause()

    assert fsm.remaining == timedelta(0)
    fsm.resume()
    fsm.advance()  # overdue segment closes immediately
    assert fsm.timeline[0].status is SegmentStatus.COMPLETED
    assert fsm.timeline[0].ended_at == NINE.replace(hour=9, minute=25)


@pytest.mark.unit
def test_resume_then_boundary_completes_work_at_actual_time():  # T12
    fsm, clock = make_fsm()
    fsm.start()
    advance_min(clock, 24)
    fsm.pause()
    advance_min(clock, 16)  # now 09:40
    fsm.resume()
    advance_min(clock, 1)
    fsm.advance()

    assert fsm.timeline[0].ended_at == NINE.replace(hour=9, minute=41)
    assert fsm.phase is SegmentPhase.BREAK
    assert fsm.phase_ends_at == NINE.replace(hour=9, minute=46)


@pytest.mark.unit
def test_stop_during_break_keeps_completed_work():  # T13
    fsm, clock = make_fsm()
    fsm.start()
    advance_min(clock, 25)
    fsm.advance()
    advance_min(clock, 2)

    fsm.stop()

    work, brk = fsm.timeline
    assert work.status is SegmentStatus.COMPLETED
    assert brk.status is SegmentStatus.INTERRUPTED
    assert fsm.state is SessionState.STOPPED


@pytest.mark.unit
def test_single_advance_catches_up_whole_day():  # T14
    fsm, clock = make_fsm(n_slots=2)
    fsm.start()

    advance_min(clock, 60)  # 25 work + 5 break + 25 work + 5 break
    fsm.advance()

    assert fsm.state is SessionState.COMPLETED
    caught_up = fsm.timeline
    assert len(caught_up) == 3  # Q1: no trailing break after the last segment
    assert [s.phase for s in caught_up] == [
        SegmentPhase.WORK,
        SegmentPhase.BREAK,
        SegmentPhase.WORK,
    ]
    assert caught_up[-1].started_at == NINE.replace(hour=9, minute=30)

    # identical to stepwise drive (confluence, cf. P3): compare structure,
    # not per-session random segment ids
    def shape(f: SessionFSM) -> list[tuple[object, int, object, object, object]]:
        return [(s.phase, s.planned_min, s.started_at, s.ended_at, s.status) for s in f.timeline]

    fsm2, clock2 = make_fsm(n_slots=2)
    fsm2.start()
    for m in (25, 5, 25, 5):
        advance_min(clock2, m)
        fsm2.advance()
    assert shape(fsm2) == shape(fsm)


@pytest.mark.unit
def test_skip_break_starts_next_work_immediately():  # T15
    fsm, clock = make_fsm()
    fsm.start()
    advance_min(clock, 25)
    fsm.advance()
    advance_min(clock, 2)

    fsm.skip_break()

    brk = fsm.timeline[1]
    assert brk.status is SegmentStatus.COMPLETED
    assert brk.ended_at == NINE.replace(hour=9, minute=27)
    assert fsm.phase is SegmentPhase.WORK
    assert fsm.phase_ends_at == NINE.replace(hour=9, minute=52)  # 09:27 + 25


@pytest.mark.unit
def test_review_does_not_block_fsm_and_updates_average():  # T16
    fsm, clock = make_fsm()
    fsm.start()
    advance_min(clock, 25)
    fsm.advance()  # break is running now
    work_id = fsm.timeline[0].id

    review = fsm.submit_review(work_id, 4)

    assert review.score == 4
    assert fsm.state is SessionState.RUNNING  # break keeps flowing
    assert fsm.average_score == 4.0
    advance_min(clock, 5)
    fsm.advance()
    assert fsm.phase is SegmentPhase.WORK


@pytest.mark.unit
def test_review_rejects_non_completed_work_segment():  # T17
    fsm, clock = make_fsm()
    fsm.start()
    advance_min(clock, 10)
    fsm.stop()
    interrupted_id = fsm.timeline[0].id

    with pytest.raises(InvalidReviewError, match="not a completed work block"):
        fsm.submit_review(interrupted_id, 3)


@pytest.mark.unit
def test_review_rejects_break_segment_and_duplicates():  # T17 extended
    fsm, clock = make_fsm()
    fsm.start()
    advance_min(clock, 25)
    fsm.advance()
    work_id = fsm.timeline[0].id
    break_id = fsm.timeline[1].id

    with pytest.raises(InvalidReviewError, match="not a completed work block"):
        fsm.submit_review(break_id, 3)
    fsm.submit_review(work_id, 5)
    with pytest.raises(InvalidReviewError, match="already has a review"):
        fsm.submit_review(work_id, 1)
