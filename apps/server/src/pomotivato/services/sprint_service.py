"""SprintService: the sprint lifecycle (spec 07 §4.1-§4.2, §5.4-§5.5).

Rules split as always: single-row checks in core (V14/V15/V19-creation/
V20), cross-row invariants and lazy recompute here. E4c PR 2 changes:

- A25: the "≤1 active" guard is lifted; the overlap ban keeps "current
  sprint" unique (covers(today) matches at most one sprint by construction).
- 5.4 auto-close: active sprints whose end_date passed are completed at
  first read/write touching sprints — honest DB write (a virtual status
  would make "!" indistinguishable from a real closure). V33: closing a
  sprint never touches task rows, so a session running past midnight is
  unaffected.
- V34 gate: manual completion needs a fate decision on every unfinished
  card; the auto-close deliberately does not wait (the "!" lights instead).
- V29: deleting a sprint erases it together with its cards.
- Period freeze: an active sprint edits texts only; completed is read-only.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from pomotivato.core.clock import Clock
from pomotivato.core.errors import SprintWindowError, ValidationError
from pomotivato.core.models import CarryChoice, Sprint, SprintStatus, Task, TaskStatus
from pomotivato.core.validation import (
    validate_sprint,
    validate_sprint_activation_window,
    validate_sprint_forward,
    validate_sprint_transition,
)
from pomotivato.infra.errors import ConflictError, NotFoundError
from pomotivato.infra.repository import DayPlanRepository, SprintRepository, TaskRepository

# PATCH may retarget the period and texts; number and id are immutable.
_PATCHABLE = frozenset({"name", "goal", "done_criteria", "start_date", "end_date", "status"})
_TEXT_FIELDS = ("name", "goal", "done_criteria")


class SprintService:
    """CRUD + lifecycle for sprint containers."""

    def __init__(self, session: AsyncSession, clock: Clock) -> None:
        self._session = session
        self._sprints = SprintRepository(session)
        self._tasks = TaskRepository(session)
        self._day_plans = DayPlanRepository(session)
        self._clock = clock

    def _today(self) -> date:
        return self._clock.now().date()

    # ---- reads ---------------------------------------------------------------

    async def list(self, status: SprintStatus | None = None) -> tuple[Sprint, ...]:
        await self._auto_close_expired()
        return await self._sprints.list(status=status)

    async def get(self, sprint_id: str) -> Sprint:
        await self._auto_close_expired()
        sprint = await self._sprints.get(sprint_id)
        if sprint is None:
            msg = f"sprint {sprint_id!r} not found"
            raise NotFoundError(msg)
        return sprint

    async def tasks_of(self, sprint_id: str) -> tuple[Task, ...]:
        """Sprint card detail: every owned task, statuses included (spec 07 §6)."""
        sprint = await self.get(sprint_id)  # 404 + auto-close on read
        return await self._tasks.list_in_sprint(sprint.id)

    async def fate_counts(self) -> tuple[dict[str, int], dict[str, int]]:
        """(unfinished, carry_pending) per sprint id — one grouped scan."""
        return (
            await self._tasks.unfinished_by_sprint(),
            await self._tasks.carry_pending_by_sprint(),
        )

    # ---- writes --------------------------------------------------------------

    async def create(
        self,
        *,
        name: str | None,
        goal: str | None,
        done_criteria: str | None,
        start_date: date,
        end_date: date,
    ) -> Sprint:
        await self._auto_close_expired()
        sprint = Sprint(
            id=f"sprint-{uuid4().hex[:12]}",
            number=await self._sprints.max_number() + 1,
            start_date=start_date,
            end_date=end_date,
            name=name,
            goal=goal,
            done_criteria=done_criteria,
        )
        validate_sprint(sprint)
        try:
            # V19 creation half: no retrospective periods (DF18 retired);
            # V19 is mapped to 409 — a state-of-the-world refusal.
            validate_sprint_forward(sprint, self._today())
        except SprintWindowError as err:
            raise ConflictError(str(err)) from err
        await self._require_no_overlap(sprint)
        await self._sprints.add(sprint)
        await self._session.flush()
        return sprint

    async def patch(self, sprint_id: str, changes: dict[str, Any]) -> Sprint:
        unknown = set(changes) - _PATCHABLE
        if unknown:
            msg = f"unknown sprint fields: {sorted(unknown)}"
            raise ValidationError(msg)
        await self._auto_close_expired()
        sprint = await self.get(sprint_id)
        if "status" in changes:
            sprint = await self._transition(sprint, str(changes.pop("status")))
        # Status-only patches (activate/complete) never hit the field guards:
        # they describe the transition itself, not an edit of the container.
        if changes:
            if sprint.status is SprintStatus.COMPLETED:
                msg = f"sprint {sprint.number} is completed; it is read-only"
                raise ConflictError(msg)
            if sprint.status is SprintStatus.ACTIVE and ({"start_date", "end_date"} & set(changes)):
                msg = "sprint is active; the period is frozen (texts only can be edited)"
                raise ConflictError(msg)
            for field in (*_TEXT_FIELDS, "start_date", "end_date"):
                if field in changes:
                    sprint = replace(sprint, **{field: changes[field]})
        validate_sprint(sprint)
        await self._require_no_overlap(sprint, exclude_id=sprint.id)
        await self._sprints.put(sprint)
        await self._session.flush()
        return sprint

    async def delete(self, sprint_id: str) -> None:
        """V29 (§4.2/§5.5): erase the container WITH its cards, one transaction.

        FK-aware order: children outside the sprint get parent_id NULLed,
        then for each card the DF1 sweep (slots from every plan, segments
        detach keeping minutes, repetition rows die) and the row itself,
        and only then the sprint.
        """
        await self._auto_close_expired()
        sprint = await self.get(sprint_id)
        tasks = await self._tasks.list_in_sprint(sprint.id)
        await self._tasks.nullify_children_of(frozenset(task.id for task in tasks))
        for task in tasks:
            await self._day_plans.purge_task_references(task.id)
            await self._tasks.detach_history(task.id)
            await self._tasks.delete(task.id)
        await self._sprints.delete(sprint.id)
        await self._session.flush()

    # ---- fate decisions (A40/V34) ------------------------------------------------

    async def leave_all_open(self, sprint_id: str) -> int:
        """'Оставить все как есть' (spec 07 §4.2): LEFT for every undecided
        unfinished card, in one call. Idempotent; decided cards are never
        rewritten (V34 immutability), so a double click is harmless."""
        sprint = await self.get(sprint_id)
        tasks = await self._tasks.list_in_sprint(sprint.id)
        decided = 0
        for task in tasks:
            if task.carry_choice is not None or task.status in (
                TaskStatus.DONE,
                TaskStatus.ARCHIVED,
            ):
                continue
            await self._tasks.put(replace(task, carry_choice=CarryChoice.LEFT))
            decided += 1
        await self._session.flush()
        return decided

    # ---- internals -------------------------------------------------------------

    async def _transition(self, sprint: Sprint, new_status: str) -> Sprint:
        try:
            target = SprintStatus(new_status)
        except ValueError as err:
            msg = f"unknown sprint status: {new_status!r}"
            raise ValidationError(msg) from err
        validate_sprint_transition(sprint.status, target)
        if target is SprintStatus.ACTIVE:
            try:
                # V20/A12: activate only while at least one date is ahead.
                validate_sprint_activation_window(sprint, self._today())
            except SprintWindowError as err:
                raise ConflictError(str(err)) from err
        if target is SprintStatus.COMPLETED:
            pending = await self._tasks.count_carry_pending(sprint.id)
            if pending:
                # V34: manual closure waits for the fate menu (A40).
                msg = f"{pending} unfinished cards still need a fate decision"
                raise ConflictError(msg)
        return replace(sprint, status=target)

    async def _auto_close_expired(self) -> None:
        """5.4 lazy auto-close: active with end_date < today -> completed.

        Idempotent, catches up several sprints in one pass, ISO dates
        compare lexicographically (no timezone math). Never touches tasks
        (V33) and never waits for fate decisions (5.4).
        """
        today = self._today()
        for sprint in await self._sprints.list(status=SprintStatus.ACTIVE):
            if sprint.end_date < today:
                validate_sprint_transition(sprint.status, SprintStatus.COMPLETED)
                await self._sprints.mark_completed(sprint)
        await self._session.flush()

    async def _require_no_overlap(self, sprint: Sprint, exclude_id: str | None = None) -> None:
        hits = await self._sprints.overlapping(sprint.start_date, sprint.end_date, exclude_id)
        if hits:
            others = ", ".join(str(hit.number) for hit in hits)
            msg = f"period overlaps sprint(s) #{others}"
            raise ConflictError(msg)
