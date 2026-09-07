"""SprintService: thin named periods (spec 05 §3.10, ADR-0003 p.3).

Domain rules live in core validators (V14/V15); this service sequences
reads/writes and owns the two cross-row invariants no single row can
check: at most one ACTIVE sprint, and no period overlap with open
(planned/active) history. Completed sprints are history and may overlap.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from pomotivato.core.errors import ValidationError
from pomotivato.core.models import Sprint, SprintStatus
from pomotivato.core.validation import validate_sprint, validate_sprint_transition
from pomotivato.infra.errors import ConflictError, NotFoundError
from pomotivato.infra.repository import SprintRepository

# PATCH may retarget the period and texts; number and id are immutable.
_PATCHABLE = frozenset({"name", "goal", "done_criteria", "start_date", "end_date", "status"})


class SprintService:
    """Create, list and patch sprints; activate/completes via status."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._sprints = SprintRepository(session)

    async def create(
        self,
        *,
        name: str | None,
        goal: str | None,
        done_criteria: str | None,
        start_date: date,
        end_date: date,
    ) -> Sprint:
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
        await self._require_no_overlap(sprint)
        await self._sprints.add(sprint)
        await self._session.flush()
        return sprint

    async def list(self) -> tuple[Sprint, ...]:
        return await self._sprints.list()

    async def get(self, sprint_id: str) -> Sprint:
        sprint = await self._sprints.get(sprint_id)
        if sprint is None:
            msg = f"sprint {sprint_id!r} not found"
            raise NotFoundError(msg)
        return sprint

    async def patch(self, sprint_id: str, changes: dict[str, Any]) -> Sprint:
        unknown = set(changes) - _PATCHABLE
        if unknown:
            msg = f"unknown sprint fields: {sorted(unknown)}"
            raise ValidationError(msg)
        sprint = await self.get(sprint_id)
        if "status" in changes:
            sprint = await self._transition(sprint, str(changes.pop("status")))
        for field in ("name", "goal", "done_criteria", "start_date", "end_date"):
            if field in changes:
                sprint = replace(sprint, **{field: changes[field]})
        validate_sprint(sprint)
        await self._require_no_overlap(sprint, exclude_id=sprint.id)
        await self._sprints.put(sprint)
        await self._session.flush()
        return sprint

    async def _transition(self, sprint: Sprint, new_status: str) -> Sprint:
        try:
            target = SprintStatus(new_status)
        except ValueError as err:
            msg = f"unknown sprint status: {new_status!r}"
            raise ValidationError(msg) from err
        validate_sprint_transition(sprint.status, target)
        if (
            target is SprintStatus.ACTIVE
            and (active := await self._sprints.get_active()) is not None
            and active.id != sprint.id
        ):
            msg = f"sprint {active.number} is already active; complete it first"
            raise ConflictError(msg)
        return replace(sprint, status=target)

    async def _require_no_overlap(self, sprint: Sprint, exclude_id: str | None = None) -> None:
        hits = await self._sprints.overlapping(sprint.start_date, sprint.end_date, exclude_id)
        if hits:
            others = ", ".join(str(hit.number) for hit in hits)
            msg = f"period overlaps open sprint(s) #{others}"
            raise ConflictError(msg)
