"""Week-browser projection for GET /api/week (spec 04 §4.2, ADR-0003 п.1).

Pure function over loaded rows: past days show the persisted truth (slots,
completed blocks, scores), future days materialize active recurrence via
core expand_recurrence WITHOUT writing anything (materialization is E4b).
This screen is read-only by the E3 screen-law; planning drags arrive there.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, timedelta
from typing import Any

from pomotivato.core.models import Once, Slot, Task, TaskStatus
from pomotivato.core.schedule import expand_recurrence
from pomotivato.services.blocks import WorkBlock

ACTIVE_STATUSES = frozenset(TaskStatus) - {TaskStatus.DONE, TaskStatus.ARCHIVED}


def week_projection(
    *,
    start: date,
    days: int,
    today: date,
    plans: Mapping[date, tuple[Slot, ...]],
    blocks: tuple[WorkBlock, ...],
    scores: Mapping[str, int],
    tasks: tuple[Task, ...],
) -> dict[str, Any]:
    """Project one [start, start+days) window into week-view items."""
    tasks_by_id = {task.id: task for task in tasks}
    recurring = tuple(
        task
        for task in tasks
        if not isinstance(task.recurrence, Once)
        and task.status in ACTIVE_STATUSES
        and not task.no_timer  # DF13: errands don't appear as day work
    )
    items = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        if day <= today:
            items.append(_past_day(day, plans.get(day, ()), blocks, scores, tasks_by_id))
        else:
            # Planned list skips what the stored plan already holds: the
            # projection must match what activate would *add*, never show
            # a ghost row next to its own sector (spec 05 §3.2 preview).
            items.append(_future_day(day, plans.get(day, ()), recurring, tasks_by_id))
    return {"start": start.isoformat(), "days": days, "items": items}


def _past_day(
    day: date,
    slots: tuple[Slot, ...],
    blocks: tuple[WorkBlock, ...],
    scores: Mapping[str, int],
    tasks_by_id: dict[str, Task],
) -> dict[str, Any]:
    day_blocks = tuple(block for block in blocks if block.day == day)
    scored = [scores[block.segment_id] for block in day_blocks if block.segment_id in scores]
    # Blocks arrive in session order, so the last scored block per task is
    # simply the freshest review that day.
    last_score_by_task: dict[str | None, int] = {}
    for block in day_blocks:
        score = scores.get(block.segment_id)
        if score is not None:
            last_score_by_task[block.task_id] = score
    return {
        "date": day.isoformat(),
        "weekday": day.weekday(),
        "kind": "past",
        "summary": {
            "blocks_done": len(day_blocks),
            "focus_min": sum(block.minutes for block in day_blocks),
            "average_score": round(sum(scored) / len(scored), 2) if scored else None,
            "tasks_done": len({b.task_id for b in day_blocks if b.task_id}),
        },
        "slots": [
            {
                "sector": slot.sector,
                "task_id": slot.task_id,
                "task_title": _title(tasks_by_id.get(slot.task_id)),
                "status": tasks_by_id[slot.task_id].status.value
                if slot.task_id in tasks_by_id
                else "deleted",
                "last_score": last_score_by_task.get(slot.task_id),
            }
            for slot in slots
        ],
        "volume": len(day_blocks),
    }


def _future_day(
    day: date,
    slots: tuple[Slot, ...],
    recurring: tuple[Task, ...],
    tasks_by_id: dict[str, Task],
) -> dict[str, Any]:
    already = {slot.task_id for slot in slots}
    planned = [
        {"task_id": task.id, "title": task.title, "type": task.type.value}
        for task in recurring
        if task.id not in already and expand_recurrence(task.recurrence, day, day)
    ]
    return {
        "date": day.isoformat(),
        "weekday": day.weekday(),
        "kind": "future",
        "planned": planned,
        # E4b (spec 05 §3.8): the planning surface must show what it added —
        # real slots with titles, no scores yet (blocks cannot exist).
        "slots": [
            {
                "sector": slot.sector,
                "task_id": slot.task_id,
                "task_title": _title(tasks_by_id.get(slot.task_id)),
                "status": tasks_by_id[slot.task_id].status.value
                if slot.task_id in tasks_by_id
                else "deleted",
                "last_score": None,
            }
            for slot in slots
        ],
        "slots_count": len(slots),
        "volume": len(planned) + len(slots),
    }


def _title(task: Task | None) -> str:
    return task.title if task is not None else "(deleted)"
