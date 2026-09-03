"""Injectable clock abstraction: the only source of time for the core.

Production code uses SystemClock; tests use FakeClock so a full 25-minute
pomodoro can be "played" in zero wall-clock time (spec 01 §3).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol


class ClockError(Exception):
    """Base class for clock violations."""


class ClockRewindError(ClockError):
    """Raised when a fake clock is asked to move backwards in time.

    Monotonicity is invariant I1 of the timer spec: no core event may
    come from the past, so rewinding is refused instead of silently ignored.
    """


def as_utc(when: datetime) -> datetime:
    """Normalize an instant to tz-aware UTC, rejecting naive datetimes.

    Naive datetimes are ambiguous across timezones and have caused real
    timer bugs elsewhere, so the core refuses to interpret them.
    """
    if when.tzinfo is None or when.tzinfo.utcoffset(when) is None:
        msg = f"naive datetime rejected, pass tz-aware UTC: {when!r}"
        raise ValueError(msg)
    return when.astimezone(UTC)


class Clock(Protocol):
    """Read-only source of current time, always tz-aware UTC."""

    def now(self) -> datetime:
        """Return the current instant."""
        ...


class SystemClock:
    """Wall-clock time from the operating system."""

    def now(self) -> datetime:
        """Return the real current instant in UTC."""
        return datetime.now(UTC)


class FakeClock:
    """Manually driven clock for deterministic tests.

    Time moves only when a test says so, and never backwards (I1).
    """

    def __init__(self, start: datetime) -> None:
        self._now = as_utc(start)

    def now(self) -> datetime:
        """Return the fake current instant."""
        return self._now

    def advance(self, delta: timedelta) -> datetime:
        """Move time forward by delta and return the new instant."""
        if delta < timedelta(0):
            msg = f"clock cannot rewind, got delta {delta}"
            raise ClockRewindError(msg)
        self._now += delta
        return self._now

    def set(self, when: datetime) -> datetime:
        """Jump to an absolute instant (same instant allowed, past refused)."""
        target = as_utc(when)
        if target < self._now:
            msg = f"clock cannot rewind: {target} is before {self._now}"
            raise ClockRewindError(msg)
        self._now = target
        return self._now
