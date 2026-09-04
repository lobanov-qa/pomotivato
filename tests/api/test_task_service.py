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
def test_delete_conflicts_when_day_plan_places_task(database, call):
    async def scenario() -> Any:
        async with call() as svc:
            placed = await svc.task.create(task_factory())
            await svc.day_plan.upsert(
                day_plan_factory(date=DEFAULT_DAY, slots=(slot_factory(task_id=placed.id),))
            )
        async with call() as svc:
            await svc.task.delete(placed.id)

    with pytest.raises(ConflictError):
        asyncio.run(scenario())
