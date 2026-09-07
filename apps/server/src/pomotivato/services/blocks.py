"""Canonical projection of persisted segments into counted work blocks.

The FSM closes a work segment only when it truly finished (COMPLETED);
breaks never count as focus (spec 03 §5 rule, reused across E3 summary and
E4a dashboards so the number can never drift between screens — DRY).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from pomotivato.core.models import Segment, SegmentPhase, SegmentStatus


@dataclass(frozen=True, slots=True)
class WorkBlock:
    """One completed focus block: identity, day (UTC) and wall minutes."""

    segment_id: str
    task_id: str | None
    day: date
    minutes: int


def completed_work_blocks(segments: tuple[Segment, ...]) -> tuple[WorkBlock, ...]:
    """Project COMPLETED WORK segments with both timestamps into blocks.

    A block without started/ended is a data bug we refuse to guess about;
    wall time is what the user actually spent, pauses included (the FSM
    froze the timeline already — we only read it).
    """
    blocks: list[WorkBlock] = []
    for segment in segments:
        if (
            segment.phase is not SegmentPhase.WORK
            or segment.status is not SegmentStatus.COMPLETED
            or segment.started_at is None
            or segment.ended_at is None
        ):
            continue
        minutes = round((segment.ended_at - segment.started_at).total_seconds() / 60)
        # Same wall-minute formula as the E3 daily summary (pauses included):
        # a dashboard and the /focus panel must never disagree on one number.
        blocks.append(
            WorkBlock(
                segment_id=segment.id,
                task_id=segment.task_id,
                day=segment.started_at.date(),
                minutes=minutes,
            )
        )
    return tuple(blocks)
