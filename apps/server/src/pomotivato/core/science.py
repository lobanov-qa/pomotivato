"""Learning-science helpers: spaced repetition and planning-fallacy buffer.

Both are pure date math (spec 01 §6): spaced repetition drives the
study-task review queue (intervals 1/3/7/14/30 days), recommended_start
inverts an estimate into a "start planning by" date padded against the
planning fallacy. No clocks, no DB — E4b wires the queue into the UI.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

from pomotivato.core.errors import ValidationError
from pomotivato.core.models import RepetitionState

# Review gaps per spec: 1, 3, 7, 14, 30 days after the previous recall.
SPACED_INTERVALS_DAYS: tuple[int, ...] = (1, 3, 7, 14, 30)

LAST_INTERVAL_IDX = len(SPACED_INTERVALS_DAYS) - 1
DEFAULT_BUFFER_RATIO = 0.25


def advance_repetition(state: RepetitionState, today: date) -> RepetitionState:
    """Move the review queue one step when `today` is due (idempotent before).

    Calling it while next_due is still in the future must return the state
    unchanged, so an E2 scheduler may fire the check on every day change.
    A matured queue sticks at the last interval instead of falling off it.
    """
    if today < state.next_due:
        return state
    new_idx = min(state.interval_idx + 1, LAST_INTERVAL_IDX)
    return RepetitionState(
        task_id=state.task_id,
        interval_idx=new_idx,
        next_due=today + timedelta(days=SPACED_INTERVALS_DAYS[new_idx]),
    )


def recommended_start(
    deadline: date,
    estimate_blocks: int,
    buffer_ratio: float = DEFAULT_BUFFER_RATIO,
) -> date:
    """Latest day to start a task so the padded plan still fits the deadline.

    days_needed = ceil(blocks * (1 + buffer_ratio)) with a hard floor of
    blocks + 1: even with a zero buffer, planning a task on its deadline
    day leaves no slack. Q4 of spec 01; the result is always < deadline.
    """
    if estimate_blocks < 1:
        msg = f"estimate_blocks must be >= 1, got {estimate_blocks}"
        raise ValidationError(msg)
    if buffer_ratio < 0:
        msg = f"buffer_ratio must be >= 0, got {buffer_ratio}"
        raise ValidationError(msg)
    padded = math.ceil(estimate_blocks * (1 + buffer_ratio))
    days_needed = max(padded, estimate_blocks + 1)
    return deadline - timedelta(days=days_needed)
