"""Unit tests for the injectable clock (spec 01 §3)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from pomotivato.core.clock import (
    ClockRewindError,
    FakeClock,
    SystemClock,
    as_utc,
)

MORNING = datetime(2026, 9, 3, 9, 0, tzinfo=UTC)


@pytest.mark.unit
def test_system_clock_reports_utc_when_called():
    now = SystemClock().now()

    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)


@pytest.mark.unit
def test_as_utc_converts_offsetzone_when_called():
    tokyo = datetime(2026, 9, 3, 11, 0, tzinfo=timezone(timedelta(hours=9)))

    assert as_utc(tokyo) == datetime(2026, 9, 3, 2, 0, tzinfo=UTC)


@pytest.mark.unit
def test_as_utc_rejects_naive_datetime_when_called():
    with pytest.raises(ValueError, match="naive datetime rejected"):
        as_utc(datetime(2026, 9, 3, 9, 0))


@pytest.mark.unit
def test_fake_clock_starts_at_given_instant_when_constructed():
    assert FakeClock(MORNING).now() == MORNING


@pytest.mark.unit
def test_fake_clock_moves_forward_by_delta_when_advanced():
    clock = FakeClock(MORNING)

    assert clock.advance(timedelta(minutes=25)) == MORNING + timedelta(minutes=25)
    assert clock.now() == MORNING + timedelta(minutes=25)


@pytest.mark.unit
def test_fake_clock_advances_cumulatively_when_advanced_twice():
    clock = FakeClock(MORNING)

    clock.advance(timedelta(minutes=10))
    clock.advance(timedelta(minutes=15))

    assert clock.now() == MORNING + timedelta(minutes=25)


@pytest.mark.unit
def test_fake_clock_stays_put_when_advanced_by_zero():
    clock = FakeClock(MORNING)

    assert clock.advance(timedelta(0)) == MORNING


@pytest.mark.unit
def test_fake_clock_rejects_negative_delta_when_advanced():
    clock = FakeClock(MORNING)

    with pytest.raises(ClockRewindError, match="cannot rewind"):
        clock.advance(timedelta(minutes=-5))


@pytest.mark.unit
def test_fake_clock_rejects_past_instant_when_set():
    clock = FakeClock(MORNING)

    with pytest.raises(ClockRewindError, match="is before"):
        clock.set(MORNING - timedelta(seconds=1))


@pytest.mark.unit
def test_fake_clock_accepts_same_or_later_instant_when_set():
    clock = FakeClock(MORNING)

    clock.set(MORNING)
    later = clock.set(MORNING + timedelta(hours=1))

    assert later == MORNING + timedelta(hours=1)
    assert clock.now() == later
