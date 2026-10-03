"""Unit tests for the done-trim ordering (core/trim.py, spec 07 §4.6, V26).

The law decided on 03.10: records are written when a card finishes, the
archive sweep reads exactly them — with created_at covering legacy rows
that predate done_at.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pomotivato.core.models import Once, Task, TaskStatus, TaskType
from pomotivato.core.trim import done_sort_key, excess_done

BASE = datetime(2026, 9, 3, 9, 0, tzinfo=UTC)


def done_task(task_id: str, *, done_at: datetime | None, born: int = 0) -> Task:
    return Task(
        id=task_id,
        title=f"Card {task_id}",
        type=TaskType.NORMAL,
        important=False,
        urgent=False,
        status=TaskStatus.DONE,
        estimate_blocks=1,
        recurrence=Once(),
        created_at=BASE + timedelta(days=born),
        done_at=done_at,
    )


@pytest.mark.unit
def test_excess_archives_the_oldest_finished_first() -> None:
    """V26: over the limit, the cards that finished EARLIEST go first."""
    cards = [
        done_task("old", done_at=BASE),
        done_task("mid", done_at=BASE + timedelta(days=1)),
        done_task("new", done_at=BASE + timedelta(days=2)),
    ]

    trimmed = excess_done(cards, limit=2)

    assert [t.id for t in trimmed] == ["old"]


@pytest.mark.unit
def test_limit_zero_archives_every_done_card() -> None:
    """§4.6: limit 0 means «Готово» shows nothing — the whole set leaves."""
    cards = [done_task("a", done_at=BASE), done_task("b", done_at=BASE)]

    assert [t.id for t in excess_done(cards, 0)] == ["a", "b"]


@pytest.mark.unit
def test_legacy_rows_sort_by_created_at_then_id() -> None:
    """Cards closed before done_at existed: created_at is the fallback clock."""
    legacy = [
        done_task("late", done_at=None, born=5),
        done_task("early", done_at=None, born=1),
    ]

    assert [t.id for t in excess_done(legacy, 1)] == ["early"]


@pytest.mark.unit
def test_missing_done_at_outranks_none_only_after_real_dates() -> None:
    """Mixed pool: a real done_at later than created_at keeps the card alive,
    a legacy row born long ago still leaves first."""
    legacy = done_task("legacy", done_at=None, born=0)
    recent = done_task("fresh", done_at=BASE + timedelta(days=10), born=0)

    assert done_sort_key(legacy) < done_sort_key(recent)
    assert [t.id for t in excess_done([legacy, recent], 1)] == ["legacy"]


@pytest.mark.unit
def test_non_done_statuses_are_never_trimmed() -> None:
    """The scope list feeds everything here; only DONE is a candidate."""
    from dataclasses import replace

    backlog = replace(done_task("b", done_at=BASE), status=TaskStatus.BACKLOG)

    assert excess_done([backlog], 0) == ()
