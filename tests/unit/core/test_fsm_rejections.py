"""Unit tests for FSM command rejection matrix (spec 01 T18..T23, I4)."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from pomotivato.core.clock import FakeClock
from pomotivato.core.errors import (
    DayPlanValidationError,
    InvalidTransitionError,
)
from pomotivato.core.fsm import SessionFSM
from pomotivato.core.models import SessionState
from tests.factories.core_models import settings_factory

from .test_fsm_transitions import NINE, advance_min, make_fsm, plan_with


def _setup_running(f: SessionFSM, c: FakeClock) -> None:
    f.start()


def _setup_paused(f: SessionFSM, c: FakeClock) -> None:
    f.start()
    f.pause()


def _setup_stopped(f: SessionFSM, c: FakeClock) -> None:
    f.start()
    f.stop()


def _setup_completed(f: SessionFSM, c: FakeClock) -> None:
    f.start()
    advance_min(c, 25)
    f.advance()


# (label, plan_size, setup, rejected_command, state_stays)
REJECTED: list[tuple[str, int, Callable[[SessionFSM, FakeClock], None], str, SessionState]] = [
    ("idle-pause", 2, lambda f, c: None, "pause", SessionState.IDLE),
    ("idle-resume", 2, lambda f, c: None, "resume", SessionState.IDLE),
    ("idle-stop", 2, lambda f, c: None, "stop", SessionState.IDLE),
    ("idle-skip", 2, lambda f, c: None, "skip_break", SessionState.IDLE),
    ("running-start", 2, _setup_running, "start", SessionState.RUNNING),
    ("running-resume", 2, _setup_running, "resume", SessionState.RUNNING),
    ("running-skip-work", 2, _setup_running, "skip_break", SessionState.RUNNING),
    ("paused-start", 2, _setup_paused, "start", SessionState.PAUSED),
    ("paused-pause", 2, _setup_paused, "pause", SessionState.PAUSED),
    ("paused-skip", 2, _setup_paused, "skip_break", SessionState.PAUSED),
    ("stopped-start", 2, _setup_stopped, "start", SessionState.STOPPED),
    ("stopped-pause", 2, _setup_stopped, "pause", SessionState.STOPPED),
    ("stopped-stop", 2, _setup_stopped, "stop", SessionState.STOPPED),
    ("completed-start", 1, _setup_completed, "start", SessionState.COMPLETED),
    ("completed-pause", 1, _setup_completed, "pause", SessionState.COMPLETED),
    ("completed-stop", 1, _setup_completed, "stop", SessionState.COMPLETED),
]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("label", "size", "setup", "cmd", "stays"),
    REJECTED,
    ids=[case[0] for case in REJECTED],
)
def test_command_raises_and_machine_untouched_when_not_allowed(
    label: str,
    size: int,
    setup: Callable[[SessionFSM, FakeClock], None],
    cmd: str,
    stays: SessionState,
) -> None:
    fsm, clock = make_fsm(size)
    setup(fsm, clock)
    before = fsm.snapshot()

    with pytest.raises(InvalidTransitionError):
        getattr(fsm, cmd)()

    assert fsm.snapshot() == before  # I4: rejected command is a full no-op
    assert fsm.state is stays


@pytest.mark.unit
def test_finished_session_rejects_every_command() -> None:
    for setup, final in (
        (_setup_stopped, SessionState.STOPPED),
        (_setup_completed, SessionState.COMPLETED),
    ):
        fsm, clock = make_fsm(1)
        setup(fsm, clock)
        assert fsm.state is final
        before = fsm.snapshot()

        for cmd in ("start", "pause", "resume", "stop", "skip_break"):
            with pytest.raises(InvalidTransitionError):
                getattr(fsm, cmd)()

        assert fsm.snapshot() == before


@pytest.mark.unit
def test_constructor_rejects_empty_day_plan():
    empty = plan_with(0)
    clock = FakeClock(NINE)

    with pytest.raises(DayPlanValidationError, match="at least one slot"):
        SessionFSM(clock, empty, settings_factory())


@pytest.mark.unit
def test_non_idle_session_resume_is_refused_until_e2_rehydration():
    from pomotivato.core.models import Session
    from pomotivato.core.models import SessionState as SS

    clock = FakeClock(NINE)
    resumed = Session(id="s-old", day_plan_id="p", state=SS.RUNNING, settings=settings_factory())

    with pytest.raises(InvalidTransitionError, match="rehydration lands in E2"):
        SessionFSM(clock, plan_with(2), settings_factory(), session=resumed)
