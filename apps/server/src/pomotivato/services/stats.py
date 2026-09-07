"""Pure dashboard aggregations for GET /api/stats (spec 04 §3/§4.1).

Every function is a projection over already-loaded rows (Tasks, WorkBlocks,
Reviews) — same discipline as services/daily_summary: no arithmetic is
invented on the client, no rules are invented here. Definitions are fixed
by spec 04 §3; if a number looks wrong, the spec line is the referee.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from pomotivato.core.models import Review, Task, TaskStatus
from pomotivato.services.blocks import WorkBlock

# Quadrant keys are transport contract (spec 04 §4.1): stable across locales.
_QUADRANTS: tuple[tuple[str, bool, bool], ...] = (
    ("important_urgent", True, True),
    ("important_not_urgent", True, False),
    ("urgent_not_important", False, True),
    ("neither", False, False),
)


def heatmap_rows(blocks: tuple[WorkBlock, ...], start: date, end: date) -> list[dict[str, Any]]:
    """Per-day totals inside [start, end]; quiet days are absent, not zero."""
    by_day: dict[date, list[WorkBlock]] = {}
    for block in blocks:
        if start <= block.day <= end:
            by_day.setdefault(block.day, []).append(block)
    return [
        {
            "date": day.isoformat(),
            "blocks_done": len(day_blocks),
            "focus_min": sum(b.minutes for b in day_blocks),
        }
        for day, day_blocks in sorted(by_day.items())
    ]


def streaks(blocks: tuple[WorkBlock, ...], *, today: date) -> dict[str, Any]:
    """Current and record runs of consecutive days with >= 1 block.

    The current streak starts at `today` OR at `today - 1`: an empty
    morning must not display "streak: 0" after a month of work (spec 04 §3).
    """
    days = {block.day for block in blocks}
    record = 0
    run = 0
    previous: date | None = None
    for day in sorted(days):
        run = run + 1 if previous is not None and day - previous == timedelta(days=1) else 1
        record = max(record, run)
        previous = day

    current_started: date | None = None
    anchor: date | None = None
    if today in days:
        anchor = today
    elif today - timedelta(days=1) in days:
        anchor = today - timedelta(days=1)
    current = 0
    probe = anchor
    while probe is not None and probe in days:
        current += 1
        probe -= timedelta(days=1)
    if current and anchor is not None:
        current_started = anchor - timedelta(days=current - 1)
    return {
        "current": current,
        "current_started": current_started.isoformat() if current_started else None,
        "record": record,
        "record_started": _record_start(days, record),
    }


def _record_start(days: set[date], record: int) -> str | None:
    """ISO date where the longest chain begins (search from the newest)."""
    if record == 0:
        return None
    for day in sorted(days, reverse=True):
        chain = [day - timedelta(days=k) for k in range(record)]
        if all(d in days for d in chain):
            return chain[-1].isoformat()
    return None


def estimate_vs_fact(tasks: tuple[Task, ...], blocks: tuple[WorkBlock, ...]) -> dict[str, Any]:
    """Planned-vs-spent on DONE tasks; ratio = sum(actual)/sum(estimate).

    A DONE task without a single completed block is excluded from both sums
    (closed by hand or deleted mid-flight would fake "underestimate").
    """
    actual_by_task: dict[str, int] = {}
    for block in blocks:
        if block.task_id is not None:
            actual_by_task[block.task_id] = actual_by_task.get(block.task_id, 0) + 1
    points = []
    estimate_total = 0
    actual_total = 0
    for task in tasks:
        actual = actual_by_task.get(task.id, 0)
        if task.status is not TaskStatus.DONE or actual == 0:
            continue
        estimate_total += task.estimate_blocks
        actual_total += actual
        points.append(
            {
                "task_id": task.id,
                "title": task.title,
                "estimate": task.estimate_blocks,
                "actual": actual,
            }
        )
    ratio = round(actual_total / estimate_total, 2) if estimate_total else None
    return {"ratio": ratio, "points": points}


def quadrant_stats(
    tasks: tuple[Task, ...], blocks: tuple[WorkBlock, ...], reviews: tuple[Review, ...]
) -> list[dict[str, Any]]:
    """Eisenhower rows: finished tasks, their blocks and mean score."""
    score_by_segment = {review.segment_id: review.score for review in reviews}
    blocks_by_task: dict[str | None, int] = {}
    scores: dict[str, list[int]] = {key: [] for key, _, _ in _QUADRANTS}
    for block in blocks:
        blocks_by_task[block.task_id] = blocks_by_task.get(block.task_id, 0) + 1
    rows = []
    for key, important, urgent in _QUADRANTS:
        done = [
            t
            for t in tasks
            if t.status is TaskStatus.DONE and t.important is important and t.urgent is urgent
        ]
        for task in done:
            for block in blocks:
                if block.task_id == task.id and block.segment_id in score_by_segment:
                    scores[key].append(score_by_segment[block.segment_id])
        block_count = sum(blocks_by_task.get(task.id, 0) for task in done)
        bucket = scores[key]
        rows.append(
            {
                "key": key,
                "tasks_done": len(done),
                "blocks": block_count,
                "average_score": round(sum(bucket) / len(bucket), 2) if bucket else None,
            }
        )
    return rows


def goal_depth(tasks: tuple[Task, ...]) -> list[dict[str, Any]]:
    """Histogram 0..3 of filled scientific fields vs done ratio per bucket."""
    buckets: list[list[Task]] = [[], [], [], []]
    for task in tasks:
        if task.status is TaskStatus.ARCHIVED:
            continue
        filled = sum(1 for field in (task.done_criteria, task.benefit, task.when_then) if field)
        buckets[filled].append(task)
    return [
        {
            "filled_fields": depth,
            "tasks": len(group),
            "done_ratio": (
                round(sum(1 for t in group if t.status is TaskStatus.DONE) / len(group), 2)
                if group
                else 0.0
            ),
        }
        for depth, group in enumerate(buckets)
    ]


def parent_progress(tasks: tuple[Task, ...]) -> list[dict[str, Any]]:
    """Per parent with children: done/total (spec 04 §3)."""
    by_parent: dict[str, list[Task]] = {}
    for task in tasks:
        if task.parent_id is not None:
            by_parent.setdefault(task.parent_id, []).append(task)
    titles = {task.id: task for task in tasks}
    rows = []
    for parent_id, children in sorted(by_parent.items()):
        parent = titles.get(parent_id)
        if parent is None:
            continue
        rows.append(
            {
                "task_id": parent_id,
                "title": parent.title,
                "done_children": sum(1 for c in children if c.status is TaskStatus.DONE),
                "total_children": len(children),
            }
        )
    return rows


def zombies(
    tasks: tuple[Task, ...],
    blocks: tuple[WorkBlock, ...],
    *,
    now: datetime,
    threshold_days: int,
) -> dict[str, Any]:
    """DOING tasks idle for threshold_days+ (snapshot; trend comes in PR5).

    Idle reference = last completed block's day, else created_at. A task
    without any block is judged from creation — never from plan date.
    """
    last_seen: dict[str, date] = {}
    for block in blocks:
        if block.task_id is not None:
            current = last_seen.get(block.task_id)
            if current is None or block.day > current:
                last_seen[block.task_id] = block.day
    items: list[dict[str, Any]] = []
    for task in tasks:
        if task.status is not TaskStatus.DOING:
            continue
        anchor = last_seen.get(task.id) or task.created_at.date()
        days_stuck = (now.date() - anchor).days
        if days_stuck >= threshold_days:
            items.append({"task_id": task.id, "title": task.title, "days_stuck": days_stuck})
    items.sort(key=lambda row: -row["days_stuck"])
    return {"count": len(items), "items": items}
