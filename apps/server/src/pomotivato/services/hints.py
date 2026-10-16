"""Pure break-time hint rules (spec 05 §3.6): learning science, no guessing.

`compute_hints` is a total pure function over already-loaded rows — the
same "projection, not second brain" pattern as daily_summary/stats. It
outputs kinds + params only: the browser renders RU (and later EN) text
from the dictionary, so the server never owns prose (⚑ Q7, spec 05).

Thresholds are spec 05 ⚑ Q5 (author-approved):
  interleaving  = 3 consecutive completed work blocks on one task/parent
  einstellung   = 2 interrupted work segments for one task in a day
  overlearning  = actual work minutes exceed estimate_blocks * work_min
  frog          = frog_candidate exists, is planned today, and is untouched;
                  `next_task_id` (E4c-UX 3/5, DF28) splits the wording: the
                  frog IS the next unplayed sector (actionable as-is) or it
                  waits later in the plan (frog-pending: pull it up with the
                  live arrows of DF27)
  recall        = a spaced-repetition row due today (break only): the ladder
                  asks for its review block while the user rests
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from pomotivato.core.models import RepetitionState, SessionSettings, Task
from pomotivato.core.science import frog_candidate
from pomotivato.services.blocks import WorkBlock


@dataclass(frozen=True, slots=True)
class Hint:
    kind: str
    params: dict[str, str | int]


CONSECUTIVE_WORK_FOR_INTERLEAVING = 3
INTERRUPTIONS_FOR_EINSTELLUNG = 2


def compute_hints(
    day_blocks: tuple[WorkBlock, ...],  # COMPLETED WORK, chronologically ordered
    interrupted_task_ids: tuple[str, ...],  # interrupted WORK task ids today
    tasks_by_id: dict[str, Task],
    plan_task_ids: frozenset[str],  # today's slots (which tasks are scheduled)
    in_break: bool,
    settings: SessionSettings,
    open_task_id: str | None = None,  # WORK the user is inside right now
    open_minutes_spent: int = 0,  # minutes burned in that open segment
    next_task_id: str | None = None,  # the unplayed sector the ladder opens next
    due_recall_task_ids: frozenset[str] = frozenset(),  # repetitions due today
) -> tuple[Hint, ...]:
    """Every rule that fires, in display order; empty day -> empty list."""
    hints: list[Hint] = []
    if in_break:
        hints.append(Hint(kind="diffuse", params={}))

    streak = _interleaving_streak(day_blocks, tasks_by_id)
    if streak is not None:
        hints.append(Hint(kind="interleaving", params={"task_id": streak}))

    over = _overlearning_tasks(day_blocks, tasks_by_id, settings, open_task_id, open_minutes_spent)
    hints += [Hint(kind="overlearning", params={"task_id": task_id}) for task_id in over]

    counts: dict[str, int] = {}
    for task_id in interrupted_task_ids:
        counts[task_id] = counts.get(task_id, 0) + 1
    hints += [
        Hint(kind="einstellung", params={"task_id": task_id})
        for task_id, hits in sorted(counts.items())
        if hits >= INTERRUPTIONS_FOR_EINSTELLUNG
    ]

    frog = frog_candidate(tuple(tasks_by_id.values()))
    if (
        in_break
        and frog is not None
        and frog.id in plan_task_ids
        and not any(block.task_id == frog.id for block in day_blocks)
    ):
        # DF28 honesty: "start the next block with it" may only be said
        # when the next unplayed sector IS the frog. When the frozen ladder
        # runs something else first, the hint names the fix instead of
        # promising the impossible — the live arrows (DF27) can swap it up.
        kind = "frog" if next_task_id == frog.id else "frog-pending"
        hints.append(Hint(kind=kind, params={"task_id": frog.id}))

    # DF28: the spaced-repetition ladder speaks during rest too — a row due
    # today whose card the dial is not about to open anyway. One line, the
    # oldest due card named, so a break never becomes a second inbox.
    if in_break and due_recall_task_ids:
        untouched = sorted(
            task_id
            for task_id in due_recall_task_ids
            if task_id != next_task_id and not any(block.task_id == task_id for block in day_blocks)
        )
        if untouched:
            hints.append(Hint(kind="recall", params={"task_id": untouched[0]}))

    return tuple(hints)


def _interleaving_streak(blocks: tuple[WorkBlock, ...], tasks_by_id: dict[str, Task]) -> str | None:
    """Task id if the last N blocks hammer one task or one parent goal."""
    if len(blocks) < CONSECUTIVE_WORK_FOR_INTERLEAVING:
        return None
    group_keys: list[str] = []
    for block in blocks:
        task = tasks_by_id.get(block.task_id or "")
        if task is None:
            return None
        # A subtask counts as its parent goal: "three tomatoes of one theme"
        # is exactly the interleaving signal the science names.
        group_keys.append(task.parent_id or task.id)
    tail = group_keys[-CONSECUTIVE_WORK_FOR_INTERLEAVING:]
    return tail[0] if len(set(tail)) == 1 else None


def _overlearning_tasks(
    blocks: tuple[WorkBlock, ...],
    tasks_by_id: dict[str, Task],
    settings: SessionSettings,
    open_task_id: str | None,
    open_minutes_spent: int,
) -> tuple[str, ...]:
    """Tasks whose today's actual minutes overran their whole estimate.

    The open segment burns toward the same budget: if work + open minutes
    already exceed estimate_blocks * work_min, the user hears it now, not
    after the fifth tomato of a two-tomato task.
    """
    minutes: dict[str, int] = {}
    for block in blocks:
        if block.task_id:
            minutes[block.task_id] = minutes.get(block.task_id, 0) + block.minutes
    if open_task_id is not None and open_minutes_spent > 0:
        minutes[open_task_id] = minutes.get(open_task_id, 0) + open_minutes_spent
    return tuple(
        sorted(
            task_id
            for task_id, spent in minutes.items()
            if (task := tasks_by_id.get(task_id)) is not None
            and spent > task.estimate_blocks * settings.work_min
        )
    )


def due_on(repetitions: tuple[RepetitionState, ...], today: date) -> list[RepetitionState]:
    """Repetition states whose next_due is today or earlier, oldest first."""
    return sorted(
        (state for state in repetitions if state.next_due <= today),
        key=lambda state: (state.next_due, state.task_id),
    )
