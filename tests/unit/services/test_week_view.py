"""Unit floor for the week projection (spec 04 §4.2): pure rows in, days out."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, timedelta
from typing import Any

from pomotivato.core.models import Once, Slot, Task, TaskStatus, TaskType
from pomotivato.services.blocks import WorkBlock
from pomotivato.services.week_view import week_projection
from tests.factories.core_models import daily_recurrence, task_factory

MONDAY = date(2026, 9, 7)
TUESDAY = MONDAY + timedelta(days=1)


def _projection(
    *,
    start: date = MONDAY,
    days: int = 3,
    today: date = MONDAY,
    plans: Mapping[date, tuple[Slot, ...]] | None = None,
    blocks: tuple[WorkBlock, ...] = (),
    scores: Mapping[str, int] | None = None,
    tasks: tuple[Task, ...] = (),
) -> dict[str, Any]:
    return week_projection(
        start=start,
        days=days,
        today=today,
        plans=plans or {},
        blocks=blocks,
        scores=scores or {},
        tasks=tasks,
    )


def test_window_has_one_item_per_day_with_weekday_and_kind() -> None:
    result = _projection(days=3)

    assert [item["date"] for item in result["items"]] == [
        "2026-09-07",
        "2026-09-08",
        "2026-09-09",
    ]
    assert [item["weekday"] for item in result["items"]] == [0, 1, 2]
    assert [item["kind"] for item in result["items"]] == ["past", "future", "future"]


def test_today_counts_as_past_even_when_empty() -> None:
    item = _projection(days=1)["items"][0]

    assert item["kind"] == "past"
    assert item["summary"] == {
        "blocks_done": 0,
        "focus_min": 0,
        "average_score": None,
        "tasks_done": 0,
    }
    assert item["slots"] == []
    assert item["volume"] == 0


def test_past_day_reports_blocks_focus_and_slots_with_last_score() -> None:
    plan = {MONDAY: (Slot(sector=1, task_id="t-1"), Slot(sector=2, task_id="t-2"))}
    tasks = (
        task_factory(id="t-1", title="Habit loop", status=TaskStatus.DOING),
        task_factory(id="t-2", title="Other", status=TaskStatus.PLANNED),
    )
    blocks = (
        WorkBlock("s-1", "t-1", MONDAY, 25),
        WorkBlock("s-2", "t-1", MONDAY, 10),
    )

    item = _projection(plans=plan, blocks=blocks, scores={"s-1": 3, "s-2": 5}, tasks=tasks)[
        "items"
    ][0]

    assert item["summary"] == {
        "blocks_done": 2,
        "focus_min": 35,
        "average_score": 4.0,
        "tasks_done": 1,
    }
    assert item["slots"] == [
        {
            "sector": 1,
            "task_id": "t-1",
            "task_title": "Habit loop",
            "status": "doing",
            "last_score": 5,
        },
        {
            "sector": 2,
            "task_id": "t-2",
            "task_title": "Other",
            "status": "planned",
            "last_score": None,
        },
    ]
    assert item["volume"] == 2


def test_slot_of_deleted_task_keeps_placeholder_title() -> None:
    ghost = {MONDAY: (Slot(sector=1, task_id="gone"),)}

    item = _projection(plans=ghost, tasks=())["items"][0]

    assert item["slots"][0]["task_title"] == "(deleted)"


def test_future_day_materializes_active_recurrence_only() -> None:
    daily = task_factory(id="r-1", title="Daily jog", recurrence=daily_recurrence())
    once = task_factory(id="r-2", title="One off", recurrence=Once())
    done_habit = task_factory(
        id="r-3", title="Old habit", recurrence=daily_recurrence(), status=TaskStatus.DONE
    )
    archived = task_factory(
        id="r-4", title="Gone habit", recurrence=daily_recurrence(), status=TaskStatus.ARCHIVED
    )
    tasks = (daily, once, done_habit, archived)

    item = _projection(days=2, tasks=tasks)["items"][1]

    assert item["kind"] == "future"
    assert item["planned"] == [
        {"task_id": "r-1", "title": "Daily jog", "type": TaskType.NORMAL.value}
    ]
    assert item["slots_count"] == 0
    assert item["volume"] == 1


def test_future_day_counts_manual_plan_slots_separately() -> None:
    plan = {TUESDAY: (Slot(sector=1, task_id="x"),)}

    item = _projection(days=2, plans=plan)["items"][1]

    assert item["slots_count"] == 1
    assert item["volume"] == 1


def test_window_after_today_shows_only_future() -> None:
    result = _projection(start=TUESDAY + timedelta(days=3), days=2)

    assert {item["kind"] for item in result["items"]} == {"future"}


def test_future_day_renders_own_slots_with_titles() -> None:
    # E4b planning surface: a task dragged onto tomorrow must appear in its
    # slots (with title), not vanish behind the planned-only contract.
    jog = task_factory(id="r-1", title="Daily jog", recurrence=daily_recurrence())
    plan = {TUESDAY: (Slot(sector=1, task_id="x-1"),)}
    other = task_factory(id="x-1", title="Gig")

    item = _projection(days=2, plans=plan, tasks=(other, jog))["items"][1]

    assert item["slots"] == [
        {
            "sector": 1,
            "task_id": "x-1",
            "task_title": "Gig",
            "status": TaskStatus.BACKLOG.value,
            "last_score": None,
        }
    ]


def test_activated_task_never_ghosts_in_planned() -> None:
    # After activate, the daily task IS a slot: the recurrence preview must
    # not show a second copy of it above the sector list (spec 05 §3.2).
    jog = task_factory(id="r-1", title="Daily jog", recurrence=daily_recurrence())
    plan = {TUESDAY: (Slot(sector=1, task_id="r-1"),)}

    item = _projection(days=2, plans=plan, tasks=(jog,))["items"][1]

    assert item["planned"] == []
    assert item["slots_count"] == 1
    assert item["volume"] == 1
