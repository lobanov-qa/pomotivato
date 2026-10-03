"""«Готово» trim (spec 07 §4.6, V26/A22): pure excess selection.

The done column shows at most `done_visible_limit` cards per scope; the
oldest ones — by the moment they entered DONE (`done_at`; cards closed
before this feature fall back to `created_at`) — go to ARCHIVED. History
stays intact, ARCHIVED opens back to BACKLOG via V7. The service owns the
write; this function owns the ordering law (core coverage gate).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from pomotivato.core.models import Task, TaskStatus


def done_sort_key(task: Task) -> tuple[datetime, str]:
    """The trim clock: done_at, created_at for legacy rows; id breaks ties."""
    return (task.done_at or task.created_at, task.id)


def excess_done(tasks: Iterable[Task], limit: int) -> tuple[Task, ...]:
    """DONE cards over `limit`, oldest-finished first (limit 0 = all)."""
    done = sorted((t for t in tasks if t.status is TaskStatus.DONE), key=done_sort_key)
    return tuple(done[: max(0, len(done) - limit)])
