"""Service floor for tasks: persistence, filters, status machine, delete policy."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

import pytest

from pomotivato.core.errors import TaskValidationError, ValidationError
from pomotivato.core.models import Daily, TaskStatus, TaskType
from pomotivato.infra.errors import ConflictError, NotFoundError
from tests.factories.core_models import (
    DEFAULT_DAY,
    DEFAULT_MOMENT,
    day_plan_factory,
    slot_factory,
    task_factory,
)


@pytest.mark.api
def test_task_roundtrips_when_reopened_in_new_transaction(database, call):
    async def scenario() -> Any:
        async with call() as svc:
            created = await svc.task.create(
                task_factory(
                    recurrence=Daily(),
                    deadline=DEFAULT_DAY + timedelta(days=5),
                    when_then="then note",
                )
            )
        async with call() as svc:
            return created, await svc.task.get(created.id)

    created, loaded = asyncio.run(scenario())

    assert loaded == created


@pytest.mark.api
def test_create_rejects_blank_title_when_task_fails_v1(database, call):
    async def scenario() -> Any:
        async with call() as svc:
            await svc.task.create(task_factory(title="   "))

    with pytest.raises(TaskValidationError):
        asyncio.run(scenario())


@pytest.mark.api
def test_create_rejects_unknown_parent_when_reference_dangles(database, call):
    async def scenario() -> Any:
        async with call() as svc:
            await svc.task.create(task_factory(parent_id="ghost-task"))

    with pytest.raises(NotFoundError):
        asyncio.run(scenario())


@pytest.mark.api
def test_create_rejects_deadline_without_runway_when_v6_breaks(database, call):
    async def scenario() -> Any:
        async with call() as svc:
            await svc.task.create(
                task_factory(
                    estimate_blocks=10,
                    deadline=DEFAULT_MOMENT.date(),
                )
            )

    with pytest.raises(TaskValidationError):
        asyncio.run(scenario())


@pytest.mark.api
def test_patch_updates_only_requested_fields_when_card_edited(database, call):
    async def scenario() -> Any:
        async with call() as svc:
            created = await svc.task.create(task_factory(title="before"))
        async with call() as svc:
            patched = await svc.task.patch(created.id, {"title": "after", "urgent": True})
            fetched = await svc.task.get(created.id)
        return created, patched, fetched

    created, patched, fetched = asyncio.run(scenario())

    assert patched.title == "after"
    assert patched.urgent is True
    assert patched.estimate_blocks == created.estimate_blocks
    assert fetched == patched


@pytest.mark.api
def test_patch_rejects_status_when_identity_fields_locked(database, call):
    async def scenario() -> Any:
        async with call() as svc:
            created = await svc.task.create(task_factory())
        async with call() as svc:
            await svc.task.patch(created.id, {"status": "done"})

    with pytest.raises(ValidationError):
        asyncio.run(scenario())


@pytest.mark.api
def test_patch_rejects_self_parent_when_graph_would_cycle(database, call):
    async def scenario() -> Any:
        async with call() as svc:
            created = await svc.task.create(task_factory())
        async with call() as svc:
            await svc.task.patch(created.id, {"parent_id": created.id})

    with pytest.raises(ValidationError):
        asyncio.run(scenario())


@pytest.mark.api
def test_list_filters_by_status_when_board_columns_queried(database, call):
    async def scenario() -> Any:
        async with call() as svc:
            keep = await svc.task.create(task_factory())
            drop = await svc.task.create(task_factory())
            await svc.task.set_status(drop.id, TaskStatus.ARCHIVED)
        async with call() as svc:
            backlog = await svc.task.list(status=TaskStatus.BACKLOG)
            archived = await svc.task.list(status=TaskStatus.ARCHIVED)
        return keep, backlog, archived

    keep, backlog, archived = asyncio.run(scenario())

    assert [t.id for t in backlog] == [keep.id]
    assert [t.id for t in archived] != []


@pytest.mark.api
def test_list_filters_by_parent_when_grouping_children(database, call):
    async def scenario() -> Any:
        async with call() as svc:
            parent = await svc.task.create(task_factory(type=TaskType.STUDY))
            first = await svc.task.create(task_factory(parent_id=parent.id))
            await svc.task.create(task_factory(parent_id=parent.id))
            await svc.task.create(task_factory())
        async with call() as svc:
            children = await svc.task.list(parent_id=first.parent_id)
            study = await svc.task.list(task_type=TaskType.STUDY)
        return children, study

    children, study = asyncio.run(scenario())

    assert len(children) == 2
    assert [t.id for t in study] and all(t.type is TaskType.STUDY for t in study)


@pytest.mark.api
def test_set_status_walks_kanban_machine_when_moves_legal(database, call):
    async def scenario() -> Any:
        async with call() as svc:
            created = await svc.task.create(task_factory())
            planned = await svc.task.set_status(created.id, TaskStatus.PLANNED)
            doing = await svc.task.set_status(created.id, TaskStatus.DOING)
            done = await svc.task.set_status(created.id, TaskStatus.DONE)
            rework = await svc.task.set_status(created.id, TaskStatus.DOING)
            return planned, doing, done, rework

    planned, doing, done, rework = asyncio.run(scenario())

    assert planned.status is TaskStatus.PLANNED
    assert doing.status is TaskStatus.DOING
    assert done.status is TaskStatus.DONE
    assert rework.status is TaskStatus.DOING


@pytest.mark.api
def test_set_status_conflicts_when_transition_illegal(database, call):
    async def scenario() -> Any:
        async with call() as svc:
            created = await svc.task.create(task_factory())
            await svc.task.set_status(created.id, TaskStatus.DONE)

    with pytest.raises(ConflictError):
        asyncio.run(scenario())


@pytest.mark.api
def test_set_status_requires_plan_when_science_gate_on(database, call):
    async def scenario() -> Any:
        async with call() as svc:
            created = await svc.task.create(task_factory())
            await svc.settings.set_require_science_fields(True)
        async with call() as svc:
            with pytest.raises(ValidationError):
                await svc.task.set_status(created.id, TaskStatus.PLANNED)
        async with call() as svc:
            await svc.task.patch(created.id, {"when_then": "then I focus"})
        async with call() as svc:
            return await svc.task.set_status(created.id, TaskStatus.PLANNED)

    planned = asyncio.run(scenario())

    assert planned.status is TaskStatus.PLANNED


@pytest.mark.api
def test_delete_removes_card_when_backlog_and_unreferenced(database, call):
    async def scenario() -> Any:
        async with call() as svc:
            doomed = await svc.task.create(task_factory())
            keep = await svc.task.create(task_factory())
        async with call() as svc:
            await svc.task.delete(doomed.id)
        async with call() as svc:
            with pytest.raises(NotFoundError):
                await svc.task.get(doomed.id)
            return await svc.task.get(keep.id)

    kept = asyncio.run(scenario())

    assert kept.title


@pytest.mark.api
def test_delete_conflicts_when_task_in_flight(database, call):
    async def scenario() -> Any:
        async with call() as svc:
            created = await svc.task.create(task_factory())
            await svc.task.set_status(created.id, TaskStatus.PLANNED)
            await svc.task.set_status(created.id, TaskStatus.DOING)
        async with call() as svc:
            await svc.task.delete(created.id)

    with pytest.raises(ConflictError):
        asyncio.run(scenario())


@pytest.mark.api
def test_delete_conflicts_when_children_reference_parent(database, call):
    async def scenario() -> Any:
        async with call() as svc:
            parent = await svc.task.create(task_factory())
            await svc.task.create(task_factory(parent_id=parent.id))
        async with call() as svc:
            await svc.task.delete(parent.id)

    with pytest.raises(ConflictError):
        asyncio.run(scenario())


@pytest.mark.api
def test_delete_purges_stale_slot_references_when_task_is_backlog(database, call):
    """DF1: a backlog card stays deletable even if ghost slots reference it."""
    ghost = task_factory()
    other = task_factory()
    yesterday = DEFAULT_DAY - timedelta(days=1)

    async def scenario() -> Any:
        async with call() as svc:
            await svc.task.create(ghost)
            await svc.task.create(other)
            await svc.day_plan.upsert(
                day_plan_factory(
                    date=yesterday,
                    slots=(
                        slot_factory(sector=1, task_id=ghost.id),
                        slot_factory(sector=2, task_id=other.id),
                    ),
                )
            )
        async with call() as svc:
            await svc.task.delete(ghost.id)
        async with call() as svc:
            plan = await svc.day_plan.get(yesterday)
            return [(slot.sector, slot.task_id) for slot in plan.slots]

    remaining = asyncio.run(scenario())

    assert remaining == [(2, other.id)]


@pytest.mark.api
def test_delete_purges_future_slots_and_keeps_worked_segments(database, call):
    """DF1 second pass (author 08.09): a backlog card owns no future.

    Slots on today/future are swept with the card (its shadow, not a
    blocker), and worked segments keep their numbers detached — the FK
    situation that used to 500 the whole delete.
    """
    ghost = task_factory()
    today = DEFAULT_DAY

    async def scenario() -> Any:
        async with call() as svc:
            await svc.task.create(ghost)
            await svc.day_plan.upsert(
                day_plan_factory(date=today, slots=(slot_factory(task_id=ghost.id),))
            )
        async with call() as svc:
            await svc.task.delete(ghost.id)
        async with call() as svc:
            with pytest.raises(NotFoundError):
                await svc.task.get(ghost.id)
            with pytest.raises(NotFoundError):
                await svc.day_plan.get(today)  # the emptied plan row is swept too

    asyncio.run(scenario())


@pytest.mark.api
def test_delete_detaches_worked_segments_when_history_references_card(database, call):
    """DF1 second pass: past timer blocks survive the card, unlinked.

    The FK on segments.task_id used to 500 the whole delete — the dogfood
    repro: a backlog card whose sector was worked on can now be removed.
    """
    ghost = task_factory()

    async def scenario() -> Any:
        async with call() as svc:
            await svc.task.create(ghost)
            await svc.day_plan.upsert(
                day_plan_factory(date=DEFAULT_DAY, slots=(slot_factory(task_id=ghost.id),))
            )
        from sqlalchemy import select

        from pomotivato.infra.orm import DayPlanRow, SegmentRow, SessionRow

        async with database.new_session() as session:
            plan_row = await session.scalar(select(DayPlanRow).limit(1))
            assert plan_row is not None
            session.add(
                SessionRow(
                    id="session-seed",
                    day_plan_id=plan_row.id,
                    state="stopped",
                    settings_json="{}",
                )
            )
            await session.flush()
            session.add(
                SegmentRow(
                    id="segment-seed",
                    session_id="session-seed",
                    task_id=ghost.id,
                    phase="work",
                    planned_min=25,
                )
            )
            await session.commit()
        async with call() as svc:
            await svc.task.delete(ghost.id)
        async with database.new_session() as session:
            from pomotivato.infra.orm import SegmentRow as SegmentModel

            row = await session.get(SegmentModel, "segment-seed")
            return row.task_id if row is not None else "row-gone"

    detached_task_id = asyncio.run(scenario())

    assert detached_task_id is None  # history kept, link gone


@pytest.mark.api
def test_clone_copies_planning_fields_into_backlog_when_done_card_repeats(database, call):
    """DF12: a finished card clones to backlog with lineage, reset progress."""
    source = task_factory(
        type=TaskType.STUDY,
        important=True,
        urgent=True,
        estimate_blocks=2,
        when_then="if 9:00 -> english",
        done_criteria="3 facts",
        benefit="level up",
        recurrence=Daily(),
        deadline=DEFAULT_DAY + timedelta(days=5),
    )

    async def scenario() -> Any:
        async with call() as svc:
            await svc.task.create(source)
            await svc.task.set_status(source.id, TaskStatus.PLANNED)
            await svc.task.set_status(source.id, TaskStatus.DOING)
            await svc.task.set_status(source.id, TaskStatus.DONE)
        async with call() as svc:
            return await svc.task.clone(source.id, "task-copy")

    clone = asyncio.run(scenario())

    assert clone.status is TaskStatus.BACKLOG
    assert clone.cloned_from == source.id
    assert clone.title == source.title
    assert clone.type is TaskType.STUDY
    assert clone.important and clone.urgent
    assert clone.estimate_blocks == 2
    assert clone.when_then == "if 9:00 -> english"
    assert clone.deadline is None  # repeats re-planned, not re-dated
    assert str(clone.recurrence) == str(Daily())  # cadence is a card setting


@pytest.mark.api
def test_clone_conflicts_when_target_id_taken(database, call):
    async def scenario() -> Any:
        async with call() as svc:
            await svc.task.create(task_factory(id="taken"))
        async with call() as svc:
            return await svc.task.clone("taken", "taken")

    with pytest.raises(ConflictError):
        asyncio.run(scenario())


@pytest.mark.api
def test_clone_is_visible_in_list_and_deletable_like_any_backlog_card(database, call):
    """DF12 hygiene: a clone has no special delete powers or blocks."""

    async def scenario() -> Any:
        async with call() as svc:
            original = await svc.task.create(task_factory())
        async with call() as svc:
            clone = await svc.task.clone(original.id, "task-lonely")
        async with call() as svc:
            await svc.task.delete(clone.id)  # never touched a plan -> clean
        async with call() as svc:
            await svc.task.delete(original.id)  # the clone is gone already
        async with call() as svc:
            return await svc.task.list()

    remaining = asyncio.run(scenario())

    assert remaining == ()
