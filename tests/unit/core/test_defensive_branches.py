"""Unit tests for defensive branches across the core (coverage gate PR).

These are guard paths: constructor rejections, idle/final-state queries
and malformed serialized values. They are rarely hit by happy flows yet
each one is the difference between "loud error" and "silent corruption"
in E2 — exactly the lines mutation testing (E5a) must not find live.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from pomotivato.core.errors import (
    DayPlanValidationError,
    ValidationError,
)
from pomotivato.core.fsm import SessionFSM
from pomotivato.core.models import (
    DayPlan,
    SessionState,
    Slot,
    day_plan_from_dict,
)
from pomotivato.core.validation import validate_day_plan
from tests.factories.core_models import (
    settings_factory,
    slot_factory,
    task_factory,
)

from .test_fsm_transitions import make_fsm


@pytest.mark.unit
def test_constructor_rejects_duplicate_sectors_when_plan_is_broken():
    broken = DayPlan(
        id="p",
        date=date(2026, 9, 3),
        slots=(Slot(sector=1, task_id="a"), Slot(sector=1, task_id="b")),
    )
    fsm, _ = make_fsm(1)

    with pytest.raises(DayPlanValidationError, match="duplicate sectors"):
        SessionFSM(fsm._clock, broken, settings_factory())


@pytest.mark.unit
def test_remaining_reports_full_first_block_when_idle():
    fsm, _ = make_fsm(2)

    assert fsm.state is SessionState.IDLE
    assert fsm.remaining.total_seconds() == 25 * 60


@pytest.mark.unit
def test_remaining_is_zero_once_session_is_done():
    for finish in ("stop", "complete"):
        fsm, clock = make_fsm(1)
        fsm.start()
        if finish == "stop":
            fsm.stop()
        else:
            clock.advance(timedelta(minutes=25))
            fsm.advance()

        assert fsm.remaining == timedelta(0)


@pytest.mark.unit
def test_queries_report_empty_when_session_never_ran():
    fsm, _ = make_fsm(2)

    assert fsm.timeline == ()
    assert fsm.current_segment is None
    assert fsm.phase is None
    assert fsm.phase_ends_at is None
    assert fsm.reviews == ()
    assert fsm.average_score is None
    assert fsm.session.state is SessionState.IDLE


@pytest.mark.unit
def test_actual_worked_is_none_for_open_or_break_segments():
    fsm, clock = make_fsm(2)
    fsm.start()
    open_work = fsm.current_segment
    assert open_work is not None
    assert fsm.actual_worked(open_work.id) is None  # not ended yet

    clock.advance(timedelta(minutes=25))
    fsm.advance()
    assert fsm.actual_worked(fsm.timeline[1].id) is None  # a break, not work
    assert fsm.actual_worked("no-such-segment") is None  # unknown id


@pytest.mark.unit
def test_day_plan_validation_rejects_more_than_twelve_slots():
    tasks = {t.id: t for t in (task_factory() for _ in range(13))}
    slots = [slot_factory(sector=i + 1, task_id=next(iter(tasks))) for i in range(13)]
    plan = DayPlan(id="p", date=date(2026, 9, 3), slots=tuple(slots))

    with pytest.raises(DayPlanValidationError, match="exceeds 12 sectors"):
        validate_day_plan(plan, tasks)


@pytest.mark.unit
def test_date_parser_rejects_garbage_when_from_dict():
    data = {
        "id": "p",
        "date": "not-a-date",
        "slots": [{"sector": 1, "task_id": "t"}],
    }

    with pytest.raises(ValidationError, match="bad date"):
        day_plan_from_dict(data)


@pytest.mark.unit
def test_date_parser_accepts_native_date_object_when_from_dict():
    # E2 will sometimes hand SQLAlchemy date objects straight to the parser
    data = {
        "id": "p",
        "date": date(2026, 9, 3),
        "slots": [{"sector": 1, "task_id": "t"}],
    }

    plan = day_plan_from_dict(data)

    assert plan.date == date(2026, 9, 3)
