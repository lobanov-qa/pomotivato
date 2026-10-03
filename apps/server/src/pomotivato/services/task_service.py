"""TaskService: the kanban card use-cases (spec 02 §4).

All domain rules are enforced by pomotivato.core validators; this service
only sequences reads/writes and turns core outcomes into infra errors.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from pomotivato.core.clock import Clock
from pomotivato.core.days import (
    close_eligible,
    fold_stale_card,
    missed_ticks,
    tick_days,
    validate_ticks_not_retrospective,
)
from pomotivato.core.errors import (
    SprintMembershipError,
    StatusTransitionError,
    ValidationError,
)
from pomotivato.core.models import (
    CarryChoice,
    Once,
    OnDates,
    SprintStatus,
    Task,
    TaskStatus,
    TaskType,
)
from pomotivato.core.trim import excess_done
from pomotivato.core.validation import (
    validate_deadline_realism,
    validate_planning_ready,
    validate_status_transition,
    validate_task,
    validate_task_sprint_membership,
)
from pomotivato.infra.errors import ConflictError, NotFoundError
from pomotivato.infra.repository import DayPlanRepository, SprintRepository, TaskRepository
from pomotivato.infra.repository_sessions import SegmentRepository, SessionRepository
from pomotivato.services.settings_service import SettingsService

# Fields PATCH may touch; everything else is identity or derived.
_PATCHABLE_FIELDS = frozenset(
    {
        "title",
        "type",
        "important",
        "urgent",
        "estimate_blocks",
        "deadline",
        "parent_id",
        "when_then",
        "done_criteria",
        "benefit",
        "no_timer",
        # DF8: the sprint-day checkboxes edit the card's recurrence live.
        "recurrence",
        # E4c (A36): a card edit may move it between active sprints; an
        # explicit null takes it to the dateless "no sprint" shelf.
        "sprint_id",
    }
)


class TaskService:
    """Create, read, patch, transition and delete task cards.

    The injected clock owns "today": ticks, folds and sprint windows are all
    day-relative rules (spec 07 §5), never wall-clock accidents.
    """

    def __init__(self, session: AsyncSession, clock: Clock) -> None:
        self._session = session
        self._tasks = TaskRepository(session)
        self._day_plans = DayPlanRepository(session)
        self._sprints = SprintRepository(session)
        self._sessions = SessionRepository(session)
        self._segments = SegmentRepository(session)
        self._settings = SettingsService(session)
        self._clock = clock

    def _today(self) -> date:
        return self._clock.now().date()

    async def _require_container(self, task: Task) -> None:
        """V18/V28/V19-membership (spec 07 §5): check the card against its box.

        sprint_id=None is the sandbox shelf and always passes. A missing
        sprint is 404 (V18); a planned/completed target or a tick outside
        the period is 409 — the service turns core membership errors into
        conflicts so clients can branch like every other funnel refusal.
        """
        if task.sprint_id is None:
            return
        sprint = await self._sprints.get(task.sprint_id)
        if sprint is None:
            msg = f"sprint {task.sprint_id!r} does not exist"
            raise NotFoundError(msg)
        try:
            validate_task_sprint_membership(task, sprint)
        except SprintMembershipError as err:
            raise ConflictError(str(err)) from err

    async def _worked_days(self, task_id: str) -> frozenset[date]:
        scan = await self._segments.worked_days_by_task()
        return scan.get(task_id, frozenset())

    async def create(self, task: Task) -> Task:
        validate_task(task)
        validate_deadline_realism(task)
        # V21 rides creation too: a card is born with today or the future.
        validate_ticks_not_retrospective(Once(), task.recurrence, self._today())
        if await self._tasks.get(task.id) is not None:
            msg = f"task {task.id!r} already exists"
            raise ConflictError(msg)
        parent = task.parent_id
        if parent is not None and await self._tasks.get(parent) is None:
            msg = f"parent task {parent!r} does not exist"
            raise NotFoundError(msg)
        await self._require_container(task)
        await self._tasks.add(task)
        await self._session.flush()
        return task

    async def get(self, task_id: str) -> Task:
        task = await self._tasks.get(task_id)
        if task is None:
            msg = f"task {task_id!r} not found"
            raise NotFoundError(msg)
        return task

    async def list(
        self,
        *,
        status: TaskStatus | None = None,
        task_type: TaskType | None = None,
        parent_id: str | None = None,
        sprint_id: str | None = None,
        no_sprint: bool = False,
    ) -> tuple[Task, ...]:
        return await self._tasks.list(
            status=status,
            task_type=task_type,
            parent_id=parent_id,
            sprint_id=sprint_id,
            no_sprint=no_sprint,
        )

    async def patch(self, task_id: str, changes: dict[str, Any]) -> Task:
        unknown = changes.keys() - _PATCHABLE_FIELDS
        if unknown:
            msg = f"cannot update fields: {sorted(unknown)}"
            raise ValidationError(msg)
        task = await self.get(task_id)
        updated = replace(task, **changes)
        validate_task(updated)
        validate_deadline_realism(updated)
        if "recurrence" in changes:
            # V21 (spec 07 §5): a mark the card did not carry before may not
            # land in the past — existing history keeps its old ticks. V21 is
            # a malformed-request rule (the spec's ValidationError column),
            # so the core error rides the 422 envelope, not the 409 one.
            validate_ticks_not_retrospective(task.recurrence, updated.recurrence, self._today())
        if updated.parent_id is not None and updated.parent_id != task_id:
            if await self._tasks.get(updated.parent_id) is None:
                msg = f"parent task {updated.parent_id!r} does not exist"
                raise NotFoundError(msg)
        elif updated.parent_id == task_id:
            msg = "task cannot be its own parent"
            raise ValidationError(msg)
        # A36 single move + A13 creation + A31 marks-outside (V19/V28): one
        # gate for both paths; a card edit re-checks it against the new box.
        await self._require_container(updated)
        await self._tasks.put(updated)
        await self._session.flush()
        return updated

    async def set_status(self, task_id: str, new_status: TaskStatus) -> Task:
        task = await self.get(task_id)
        try:
            validate_status_transition(task.status, new_status)
        except StatusTransitionError as err:
            raise ConflictError(str(err)) from err
        if new_status is TaskStatus.PLANNED:
            require = await self._settings.require_science_fields()
            validate_planning_ready(task, require)
        if new_status is TaskStatus.DONE and task.status is not TaskStatus.DONE:
            # V31 (spec 07): neither a future tick nor a missed one lets a
            # sprint card into «Готово» by drag — the walk after the blocks
            # does that, with the same checks.
            await self._require_done_clean(task)
        if new_status is TaskStatus.DOING and task.status is not TaskStatus.DOING:
            # V27 (A23): "В работе" is a card of today — its sprint must
            # cover the date (the shelf has no dates and is always allowed).
            await self._require_covers_today(task)
            # Funnel law: "В работе" == today == the dial; the capacity is
            # a server-side gate so no client (or second window) overflows.
            # DF13: no-timer errands don't consume the dial — free to carry.
            limit = (await self._settings.get_ui_settings()).max_in_work
            in_work = await self._tasks.list(status=TaskStatus.DOING)
            timer_load = sum(1 for t in in_work if not t.no_timer)
            if not task.no_timer and timer_load >= limit:
                msg = f"only {limit} tasks fit in work today"
                raise ConflictError(msg)
        if new_status is TaskStatus.DONE and task.status is not TaskStatus.DONE:
            # One door for every arrival into «Готово»: the trim (V26) must
            # not be skippable by which route the card came in.
            return await self.complete(task.id)
        updated = replace(task, status=new_status)
        if new_status is TaskStatus.DOING:
            # A28: entering work on an unmarked day marks it — the plan and
            # the fact stay honest, the day can later go missed the normal way.
            updated = self._ensure_today_tick(updated)
        await self._tasks.put(updated)
        await self._session.flush()
        return updated

    async def complete(self, task_id: str) -> Task:
        """V26 (spec 07 §4.6): the only door into «Готово».

        Stamps done_at (the trim clock, the author's 03.10 decision: records
        are written when a card finishes and the archive sweep reads exactly
        them) and trims the card's own scope to done_visible_limit — the
        oldest finished surplus goes to ARCHIVED, history intact.
        """
        task = await self.get(task_id)
        if task.status is not TaskStatus.DONE:
            closed = replace(task, status=TaskStatus.DONE, done_at=self._clock.now())
            await self._tasks.put(closed)
            await self._session.flush()
            task = closed
        await self._trim_done_scope(task.sprint_id)
        # The trim may have archived this very card (limit 0 — the spec
        # says so honestly); re-read, never return a stale DONE.
        return await self.get(task.id)

    async def _trim_done_scope(self, sprint_id: str | None) -> None:
        """Archive the done surplus of one scope (shelf: sprint_id None)."""
        limit = (await self._settings.get_ui_settings()).done_visible_limit
        scope = await self._tasks.list(sprint_id=sprint_id, no_sprint=sprint_id is None)
        for stale in excess_done(scope, limit):
            await self._tasks.put(replace(stale, status=TaskStatus.ARCHIVED))
        await self._session.flush()

    async def _require_done_clean(self, task: Task) -> None:
        """V31 (spec 07): a sprint card with a hole never reaches «Готово».

        Both kinds of hole block the drag: a tick still ahead (the days
        have to be worked) and a missed tick in the past (S1: remove the
        mark or work the day — the card waits for the decision).
        """
        if task.sprint_id is None:
            return
        today = self._today()
        worked = await self._worked_days(task.id)
        ahead = sorted(day for day in tick_days(task) if day > today)
        if ahead:
            msg = f"card still has planned days ahead: {ahead[0].isoformat()}"
            raise ConflictError(msg)
        missed = missed_ticks(task, today, worked)
        if missed:
            msg = f"card has a missed day: {missed[0].isoformat()}"
            raise ConflictError(msg)

    async def close(self, task_id: str) -> Task:
        """V32/A35 (spec 07): close a card whose dates ran out, no timer rerun.

        The user confirms through the dialog; the endpoint re-checks the
        same conditions the hint offers them by (a completed block exists,
        no future and no unworked ticks remain) so a stale client cannot
        close a card that gained days in another window.
        """
        task = await self.get(task_id)
        if task.status is TaskStatus.DONE:
            return task
        today = self._today()
        worked = await self._worked_days(task.id)
        if not close_eligible(task, today, worked):
            msg = "card is not closeable: work exists, dates ahead or ticks unspent"
            raise ConflictError(msg)
        return await self.complete(task.id)

    async def fold_yesterday(self) -> tuple[Task, ...]:
        """V30+V33 (spec 07 §5.7): the lazy day fold, first read of a new day.

        A card left in DOING without sectors in today's plan goes back to
        PLANNED (or DONE when every tick was worked). V33: cards of a live
        session — including the completed-but-unreviewed tail that keeps
        the review window open — are never folded; their blocks belong to
        the day they started. no_timer errands are off the dial and by
        definition have no sectors, folding them would be a lie.
        """
        today = self._today()
        plan = await self._day_plans.get_by_date(today)
        sectors = {slot.task_id for slot in plan.slots} if plan else set()
        live_tasks = await self._live_session_task_ids()
        worked_scan = await self._segments.worked_days_by_task()
        folded: list[Task] = []
        for task in await self._tasks.list(status=TaskStatus.DOING):
            if task.no_timer or task.id in sectors or task.id in live_tasks:
                continue
            nxt = fold_stale_card(task, today, worked_scan.get(task.id, frozenset()))
            if nxt is not None and nxt is not task.status:
                if nxt is TaskStatus.DONE:
                    folded.append(await self.complete(task.id))
                    continue
                moved = replace(task, status=nxt)
                await self._tasks.put(moved)
                folded.append(moved)
        if folded:
            await self._session.flush()
        return tuple(folded)

    async def _live_session_task_ids(self) -> frozenset[str]:
        """Task ids of RUNNING/PAUSED rows (V33's shield)."""
        ids: set[str] = set()
        for stored in await self._sessions.list_live():
            if stored.slots:
                ids.update(slot.task_id for slot in stored.slots)
        return frozenset(ids)

    async def _require_covers_today(self, task: Task) -> None:
        if task.sprint_id is None:
            return
        sprint = await self._sprints.get(task.sprint_id)
        if sprint is None or not sprint.covers(self._today()):
            msg = "move the card to the sprint that covers today, or to no sprint"
            raise ConflictError(msg)

    def _ensure_today_tick(self, task: Task) -> Task:
        today = self._today()
        if task.no_timer or task.sprint_id is None:
            return task
        if today in tick_days(task):
            return task
        marked = OnDates(frozenset(tick_days(task) | {today}))
        return replace(task, recurrence=marked)

    async def clone(self, task_id: str, clone_id: str) -> Task:
        """Duplicate a finished card back into the backlog (spec 06 DF12).

        The point (author 08.09) is not re-creating a big repeated task
        from scratch: title, type, quadrant, chunk, when_then/criteria/
        benefit and recurrence cadence all carry over. What resets:
        status -> backlog, deadline -> None (a past date must not haunt
        the copy), and `cloned_from` records the lineage for history.
        """
        task = await self.get(task_id)
        if await self._tasks.get(clone_id) is not None:
            msg = f"task {clone_id!r} already exists"
            raise ConflictError(msg)
        clone = replace(
            task,
            id=clone_id,
            status=TaskStatus.BACKLOG,
            deadline=None,
            cloned_from=task.id,
        )
        validate_task(clone)
        # E4c/V28: a clone lands where its card lands — the same container
        # gates run (a copy may not settle into a completed/planned sprint).
        await self._require_container(clone)
        await self._tasks.add(clone)
        await self._session.flush()
        return clone

    async def resolve_carry(
        self, task_id: str, *, target_sprint_id: str | None, leave: bool, today: date
    ) -> Task:
        """V34/A40 (spec 07 §4.2): the fate menu for one unfinished card.

        Three answers: a target ACTIVE sprint, the dateless shelf (None),
        or 'leave' — the card freezes with its closed sprint forever. Move
        and shelf are COPIES (A27): the original keeps its history row and
        gets MOVED, the copy gets a new id, BACKLOG status, Once recurrence
        (day ticks reset), and the deadline only if still real (A19). The
        decision is immutable: a second call is a 409, not a re-write.
        """
        task = await self.get(task_id)
        if task.sprint_id is None:
            msg = "a card without a sprint has no carry decision to make"
            raise ConflictError(msg)
        if task.carry_choice is not None:
            msg = f"fate of task {task_id!r} is already {task.carry_choice.value}"
            raise ConflictError(msg)
        if task.status in (TaskStatus.DONE, TaskStatus.ARCHIVED):
            msg = "finished cards stay in the sprint history; nothing to carry"
            raise ConflictError(msg)
        if leave:
            decided = replace(task, carry_choice=CarryChoice.LEFT)
            await self._tasks.put(decided)
            await self._session.flush()
            return decided
        if target_sprint_id is not None:
            sprint = await self._sprints.get(target_sprint_id)
            if sprint is None:
                msg = f"sprint {target_sprint_id!r} does not exist"
                raise NotFoundError(msg)
            if sprint.status is not SprintStatus.ACTIVE:
                msg = f"sprint {sprint.number} is not activated; carry needs an active sprint"
                raise ConflictError(msg)
        copy = replace(
            task,
            id=f"task-{uuid4().hex[:12]}",
            status=TaskStatus.BACKLOG,
            recurrence=Once(),
            # A19: a deadline travels only while it still means something.
            deadline=task.deadline if (task.deadline and task.deadline >= today) else None,
            cloned_from=task.id,
            sprint_id=target_sprint_id,
            carry_choice=None,
        )
        validate_task(copy)
        await self._require_container(copy)
        decided = replace(task, carry_choice=CarryChoice.MOVED)
        await self._tasks.add(copy)
        await self._tasks.put(decided)
        await self._session.flush()
        return decided

    async def delete(self, task_id: str) -> None:
        task = await self.get(task_id)
        # Q3 of spec 02: only cards that never entered work are forgettable.
        if task.status not in (TaskStatus.BACKLOG, TaskStatus.ARCHIVED):
            msg = f"only backlog/archived tasks can be deleted, {task.status.value} survives"
            raise ConflictError(msg)
        if await self._tasks.has_children(task_id):
            msg = f"task {task_id!r} still has children"
            raise ConflictError(msg)
        # DF1 of spec 06 (author 08.09, second pass): a backlog card owns
        # no future — every slot referencing it, past or planned, is its
        # shadow and is swept first; worked segments detach, not vanish.
        await self._day_plans.purge_task_references(task_id)
        await self._tasks.detach_history(task_id)
        await self._tasks.delete(task_id)
        await self._session.flush()
