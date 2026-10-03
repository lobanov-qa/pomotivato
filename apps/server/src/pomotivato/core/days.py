"""Day-close rules: the card's day walk (spec 07 §5.1/§5.7, E4c PR 4).

Pure core: no clocks, no storage. The services feed today, the day plan
counts and the worked-days scan in; these functions answer what happens to
the card. This is where the author's two 24.09 bugs died: the card no
longer escapes «В работе» after the FIRST block of two (V22 checks the
day's blocks first), and past days can no longer be ticked (V21).

Definitions (5.7):
    tick        = a day marked on a sprint card (OnDates)
    worked      = a tick whose day carries a completed WORK segment
    missed      = a worked-less tick in the past (V31 blocks DONE)
    day blocks  = sectors the card owns in TODAY's plan (estimate per day)
"""

from __future__ import annotations

from datetime import date

from pomotivato.core.errors import RecurrenceValidationError
from pomotivato.core.models import OnDates, Recurrence, Task, TaskStatus


def tick_days(task: Task) -> frozenset[date]:
    """The card's marked days; empty for every non-ticked recurrence (A8)."""
    if isinstance(task.recurrence, OnDates):
        return task.recurrence.days
    return frozenset()


def worked_ticks(task: Task, worked_days: frozenset[date]) -> frozenset[date]:
    return tick_days(task) & worked_days


def missed_ticks(task: Task, today: date, worked_days: frozenset[date]) -> tuple[date, ...]:
    """S7: marks in the past without a completed block, oldest first."""
    return tuple(sorted(day for day in tick_days(task) if day < today and day not in worked_days))


def future_ticks(task: Task, today: date) -> tuple[date, ...]:
    return tuple(sorted(day for day in tick_days(task) if day > today))


def all_ticks_worked(task: Task, worked_days: frozenset[date]) -> bool:
    return not (tick_days(task) - worked_days)


def close_eligible(task: Task, today: date, worked_days: frozenset[date]) -> bool:
    """V32 (A35): the card may close by decision, no timer re-run.

    Needs a finished block (worked_days non-empty: a never-worked card
    waits for real work) and no ticks left — neither future nor missed.
    """
    return (
        bool(worked_days) and not future_ticks(task, today) and all_ticks_worked(task, worked_days)
    )


def walk_after_day(
    task: Task,
    today: date,
    *,
    day_blocks: int,
    blocks_done_today: int,
    worked_days: frozenset[date],
) -> TaskStatus | None:
    """V22: the card's verdict once a review (or its skip) closed a block.

    Returns the new status, or None meaning "stay where you are". The
    day's blocks come FIRST: a two-sector card that scored its first
    block stays in DOING — the author's bug (1) from 24.09, fixed here.
    (a) blocks remain           -> stay DOING
    (b) future ticks            -> PLANNED
    (в) missed/unworked ticks   -> PLANNED (V31 forbids DONE through a hole)
    (г) everything worked       -> DONE
    (д) card without a sprint   -> DONE once the day's blocks are gone
    """
    if task.sprint_id is None:
        return TaskStatus.DONE if blocks_done_today >= max(day_blocks, 1) else None
    if blocks_done_today < max(day_blocks, 1):
        return None
    if future_ticks(task, today):
        return TaskStatus.PLANNED
    if not all_ticks_worked(task, worked_days):
        return TaskStatus.PLANNED
    return TaskStatus.DONE


def fold_stale_card(task: Task, today: date, worked_days: frozenset[date]) -> TaskStatus | None:
    """V30: a DOING card without a sector in today's plan, seen on a new day.

    PLANNED while unworked ticks remain, DONE once they are all behind it.
    A card that never produced a completed block goes to PLANNED, not DONE
    (S15: a vanished plan must not fake a finished card). The caller owns
    V33 (live sessions are never folded) and no_timer errands (they are not
    on the dial, absence means nothing here).
    """
    if future_ticks(task, today) or not all_ticks_worked(task, worked_days):
        return TaskStatus.PLANNED
    if not worked_days:
        return TaskStatus.PLANNED
    return TaskStatus.DONE


def validate_ticks_not_retrospective(old: Recurrence, new: Recurrence, today: date) -> None:
    """V21: a mark that was not on the card before may not be in the past.

    Existing past marks live on (the card returns to plan with its
    history); only a NEW day strictly before today is refused — the
    author's bug (2) from 24.09 ("the label can be put on a past day").
    """
    if not isinstance(new, OnDates):
        return
    previous = old.days if isinstance(old, OnDates) else frozenset[date]()
    too_old = sorted(day for day in new.days - previous if day < today)
    if too_old:
        listed = ", ".join(day.isoformat() for day in too_old)
        msg = f"cannot mark days in the past: {listed}"
        raise RecurrenceValidationError(msg)
