"""Unit tests for E4b modes: special breaks, strict mode, warm-up (spec 05 §3.3-3.5)."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta, timezone

import pytest

from pomotivato.core.clock import FakeClock
from pomotivato.core.errors import InvalidTransitionError, SettingsValidationError
from pomotivato.core.fsm import SessionFSM
from pomotivato.core.models import SegmentPhase, SegmentStatus, SessionState
from pomotivato.core.validation import validate_settings
from tests.factories.core_models import settings_factory, special_break_factory

from .test_fsm_transitions import NINE, make_fsm, plan_with, state_of

# Sessions start at 09:00 UTC in a fixed +03:00 zone, so local wall time
# = UTC + 3. Anchors below pick exact cascade moments: 12:10 local is
# 09:10 UTC (inside the first 25-min block), 13:00 local is 10:00 UTC.
TZ_UTC3 = timezone(timedelta(hours=3))
LUNCH_1010 = time(12, 10)  # 09:10 UTC — strictly inside work#1
LUNCH_1300 = time(13, 0)  # 10:00 UTC — between blocks, trailing cases


def make_lunch_fsm(n_slots: int = 3, **settings_kw: object) -> tuple[SessionFSM, FakeClock]:
    merged: dict[str, object] = {
        "work_min": 25,
        "break_min": 5,
        "warmup_min": 0,
        "special_breaks": [special_break_factory(at=LUNCH_1010)],
    }
    merged.update(settings_kw)
    clock = FakeClock(NINE)
    fsm = SessionFSM(clock, plan_with(n_slots), settings_factory(**merged), tz=TZ_UTC3)
    return fsm, clock


# ---------------------------------------------------------------- special breaks


@pytest.mark.unit
def test_special_break_cuts_open_work_and_keeps_remaining_ladder():  # GWT-B1
    fsm, clock = make_lunch_fsm()
    fsm.start()  # work#1: 09:00-09:25Z
    clock.advance(timedelta(minutes=45))  # 09:45Z: lunch (09:10Z) was crossed

    fsm.advance()

    timeline = fsm.timeline
    # work#1 cut at the anchor; the special ran 09:10-09:40 and closed in
    # the same cascade; work#2 auto-started at 09:40 and is still open.
    assert [s.phase for s in timeline] == [
        SegmentPhase.WORK,
        SegmentPhase.SPECIAL_BREAK,
        SegmentPhase.WORK,
    ]
    assert timeline[0].status is SegmentStatus.INTERRUPTED
    assert timeline[0].ended_at == NINE + timedelta(minutes=10)
    special = timeline[1]
    assert special.started_at == NINE + timedelta(minutes=10)
    assert special.planned_min == 30
    assert special.status is SegmentStatus.COMPLETED
    assert special.break_label == "lunch"
    assert timeline[2].started_at == NINE + timedelta(minutes=40)
    assert state_of(fsm) is SessionState.RUNNING


@pytest.mark.unit
def test_paused_over_anchor_is_not_applied_retroactively():  # GWT-B2
    fsm, clock = make_lunch_fsm()
    fsm.start()  # work until 09:25Z
    clock.advance(timedelta(minutes=20))  # 09:20Z inside first work block
    fsm.pause()
    clock.advance(timedelta(minutes=60))  # lunch (10:00Z) burned while paused

    fsm.advance()  # must be a no-op in PAUSED
    fsm.resume()
    fsm.advance()

    # resume re-anchors the deadline from the resume moment; no special
    # segment was inserted for a lunch the user lived through on their own.
    assert all(s.phase is not SegmentPhase.SPECIAL_BREAK for s in fsm.timeline)


@pytest.mark.unit
def test_two_anchors_in_one_advance_apply_in_order():  # GWT-B3 (confluence)
    breaks = [
        special_break_factory(at=time(13, 0), duration_min=15),
        special_break_factory(at=time(14, 0), duration_min=15),
    ]
    fsm, clock = make_lunch_fsm(n_slots=4, special_breaks=breaks)
    fsm.start()
    clock.advance(timedelta(hours=6))  # far past both anchors

    fsm.advance()

    specials = [s for s in fsm.timeline if s.phase is SegmentPhase.SPECIAL_BREAK]
    assert len(specials) == 2
    assert specials[0].started_at is not None and specials[1].started_at is not None
    assert specials[0].started_at < specials[1].started_at


@pytest.mark.unit
def test_special_after_last_work_still_happens_then_day_completes():  # GWT-B4
    # 1 slot, ladder would end 09:30Z; lunch at 10:00Z is crossed on the
    # way to 10:15Z — it materializes as a trailing special segment first.
    fsm, clock = make_lunch_fsm(n_slots=1, special_breaks=[special_break_factory(at=LUNCH_1300)])
    fsm.start()
    clock.advance(timedelta(hours=1, minutes=15))  # 10:15Z

    fsm.advance()

    assert state_of(fsm) is SessionState.RUNNING  # trailing special still open
    assert fsm.phase is SegmentPhase.SPECIAL_BREAK
    clock.advance(timedelta(minutes=30))  # 10:45Z: lunch ends
    fsm.advance()
    assert state_of(fsm) is SessionState.COMPLETED


@pytest.mark.unit
def test_boundary_anchor_on_work_deadline_replaces_scheduled_break():
    # lunch lands exactly when the first block ends (12:25 local == work
    # deadline 09:25Z under +03:00)
    brk = special_break_factory(at=time(12, 25), duration_min=20, label="edge")
    fsm, clock = make_lunch_fsm(n_slots=2, special_breaks=[brk])
    fsm.start()
    clock.advance(timedelta(minutes=25))

    fsm.advance()

    phases = [s.phase for s in fsm.timeline]
    assert phases == [SegmentPhase.WORK, SegmentPhase.SPECIAL_BREAK]
    assert fsm.timeline[1].break_label == "edge"
    assert fsm.timeline[0].status is SegmentStatus.COMPLETED


@pytest.mark.unit
def test_no_special_breaks_keeps_legacy_cascade_bit_identical():  # GWT-E2 shape
    fsm, clock = make_fsm(2)
    fsm.start()
    clock.advance(timedelta(minutes=31))
    fsm.advance()
    phases = [s.phase for s in fsm.timeline]
    assert phases == [SegmentPhase.WORK, SegmentPhase.BREAK, SegmentPhase.WORK]


# ---------------------------------------------------------------- strict mode


@pytest.mark.unit
def test_pause_is_refused_in_strict_mode_while_working():  # GWT-D1
    fsm, _clock = make_fsm(2, strict_mode=True)
    fsm.start()

    with pytest.raises(InvalidTransitionError, match="strict"):
        fsm.pause()

    assert state_of(fsm) is SessionState.RUNNING
    assert fsm.phase is SegmentPhase.WORK


@pytest.mark.unit
def test_pause_is_allowed_in_strict_mode_during_break():  # GWT-D2
    fsm, clock = make_fsm(2, strict_mode=True)
    fsm.start()
    clock.advance(timedelta(minutes=26))
    fsm.advance()

    fsm.pause()  # open segment is a BREAK: strict protects WORK only

    assert state_of(fsm) is SessionState.PAUSED


@pytest.mark.unit
def test_stop_is_always_allowed_in_strict_mode():  # GWT-D3
    fsm, clock = make_fsm(2, strict_mode=True)
    fsm.start()
    clock.advance(timedelta(minutes=10))

    fsm.stop("panic")

    assert state_of(fsm) is SessionState.STOPPED


@pytest.mark.unit
def test_skip_break_in_strict_mode_still_works():
    # strict mode protects work pacing, not break ending (spec 05: skip of
    # an open BREAK stays available; T15 semantics unchanged)
    fsm, clock = make_fsm(2, strict_mode=True)
    fsm.start()
    clock.advance(timedelta(minutes=26))
    fsm.advance()

    fsm.skip_break()

    assert fsm.phase is SegmentPhase.WORK


# ---------------------------------------------------------------- warm-up


@pytest.mark.unit
def test_first_segment_is_warmup_then_full_rhythm():  # GWT-E1
    fsm, clock = make_fsm(3, warmup_min=5)
    fsm.start()

    assert fsm.timeline[0].planned_min == 5
    clock.advance(timedelta(minutes=10))  # warm block done, break starts
    fsm.advance()
    clock.advance(timedelta(minutes=6))
    fsm.advance()
    assert fsm.timeline[-1].phase is SegmentPhase.WORK
    assert fsm.timeline[-1].planned_min == 25  # work_min returns after warm-up


@pytest.mark.unit
def test_warmup_zero_keeps_first_block_at_work_min():  # GWT-E2
    fsm, _clock = make_fsm(1, warmup_min=0)
    fsm.start()
    assert fsm.timeline[0].planned_min == 25


@pytest.mark.unit
def test_idle_remaining_reports_warmup_length():
    clock = FakeClock(NINE)
    fsm = SessionFSM(
        clock,
        plan_with(1),
        settings_factory(warmup_min=7),
        tz=UTC,
    )
    assert fsm.remaining == timedelta(minutes=7)


# ---------------------------------------------------------------- V12/V13


def _expect_settings_error(**kwargs: object) -> None:
    validate_settings(settings_factory(**kwargs))


@pytest.mark.unit
def test_warmup_above_30_is_rejected():
    with pytest.raises(SettingsValidationError, match="warmup_min"):
        _expect_settings_error(warmup_min=31)


@pytest.mark.unit
def test_special_break_duration_and_duplicate_time_are_rejected():
    with pytest.raises(SettingsValidationError, match="duration"):
        _expect_settings_error(special_breaks=(special_break_factory(duration_min=4),))
    with pytest.raises(SettingsValidationError, match="duplicate"):
        _expect_settings_error(special_breaks=(special_break_factory(), special_break_factory()))


@pytest.mark.unit
def test_more_than_three_special_breaks_is_rejected():
    breaks = tuple(special_break_factory(at=time(12, m)) for m in range(4))
    with pytest.raises(SettingsValidationError, match="special breaks"):
        _expect_settings_error(special_breaks=breaks)


# ---------------------------------------------------------------- settings wire


@pytest.mark.unit
def test_settings_wire_roundtrip_with_special_breaks():
    from pomotivato.core.models import (
        SessionSettings,
        session_settings_from_dict,
        to_dict,
    )

    original = SessionSettings(
        strict_mode=True,
        warmup_min=5,
        special_breaks=(special_break_factory(),),
    )
    parsed = session_settings_from_dict(to_dict(original))
    assert parsed == original


@pytest.mark.unit
def test_legacy_settings_json_loads_with_e4b_defaults():
    from pomotivato.core.models import session_settings_from_dict

    legacy = {
        "work_min": 30,
        "break_min": 6,
        "long_break_min": 18,
        "long_break_every": 3,
        "auto_start_next": False,
    }
    parsed = session_settings_from_dict(legacy)
    assert parsed.special_breaks == ()
    assert parsed.warmup_min == 0 and parsed.strict_mode is False
    assert parsed.work_min == 30 and parsed.auto_start_next is False


# ---------------------------------------------------------------- tz plumbing


@pytest.mark.unit
def test_anchor_evaluates_in_injected_local_zone():
    # +07:00 (Novosibirsk): 13:00 local = 06:00Z -> anchor inside a 05:00Z start
    clock = FakeClock(datetime(2026, 9, 3, 5, 0, tzinfo=UTC))
    fsm = SessionFSM(
        clock,
        plan_with(2),
        settings_factory(
            work_min=200,  # long enough that lunch is strictly inside
            special_breaks=[special_break_factory()],
        ),
        tz=timezone(timedelta(hours=7)),
    )
    fsm.start()
    clock.advance(timedelta(hours=8, minutes=10))  # 13:10 local

    fsm.advance()

    specials = [s for s in fsm.timeline if s.phase is SegmentPhase.SPECIAL_BREAK]
    assert len(specials) == 1
    assert specials[0].started_at == datetime(2026, 9, 3, 6, 0, tzinfo=UTC)
