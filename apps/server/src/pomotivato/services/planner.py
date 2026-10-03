"""Pure day-plan mutation helpers for add (spec 05 §3.8; E4c §9).

The drag-to-plan primitive: append the task's chunk (estimate_blocks slots,
V10 cap) to the first free sectors. What does not fit is reported, never
silently lost — the response carries `skipped` so the week screen can say
so honestly. `activate_recurring` died with the "Repeat into plan" button
(spec 07 A11): the plan is derived from the doing column, day marks live
on the card.
"""

from __future__ import annotations

from dataclasses import dataclass

from pomotivato.core.models import MAX_SECTOR, DayPlan, Slot, Task


@dataclass(frozen=True, slots=True)
class AddOutcome:
    """Result of a mutation request: new plan + who got in / squeezed out."""

    plan: DayPlan
    added: tuple[str, ...]
    skipped: tuple[str, ...]


def _next_free_sector(plan: DayPlan) -> int | None:
    used = {slot.sector for slot in plan.slots}
    for sector in range(1, MAX_SECTOR + 1):
        if sector not in used:
            return sector
    return None


def add_task_to_plan(plan: DayPlan, task: Task) -> AddOutcome:
    """Append task slots up to its chunk size; V10 is the ceiling per task.

    An already-scheduled task is a no-op add (idempotence: GWT-A2) — the
    caller still reports it as added only when real slots appeared.
    """
    existing = sum(1 for slot in plan.slots if slot.task_id == task.id)
    allowed = max(task.estimate_blocks, 1)
    if existing >= allowed:
        # Fully scheduled already: idempotent no-op, not a capacity miss.
        return AddOutcome(plan=plan, added=(), skipped=())
    slots: list[Slot] = list(plan.slots)
    added_count = 0
    while existing + added_count < allowed:
        sector = _next_free_sector(DayPlan(id=plan.id, date=plan.date, slots=tuple(slots)))
        if sector is None:
            break
        slots.append(Slot(sector=sector, task_id=task.id))
        added_count += 1
    new_plan = DayPlan(id=plan.id, date=plan.date, slots=tuple(slots))
    if added_count == 0:
        return AddOutcome(plan=new_plan, added=(), skipped=(task.id,))
    return AddOutcome(plan=new_plan, added=(task.id,), skipped=())
