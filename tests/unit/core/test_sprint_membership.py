"""Unit tests for sprint container rules V19/V28 (spec 07 §5, E4c PR 1)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from pomotivato.core.errors import SprintMembershipError, SprintWindowError
from pomotivato.core.models import Once, OnDates, Sprint, SprintStatus, task_from_dict, task_to_dict
from pomotivato.core.validation import validate_sprint_forward, validate_task_sprint_membership
from tests.factories.core_models import next_id, task_factory

TODAY = date(2026, 9, 3)


def sprint_factory(**overrides: object) -> Sprint:
    args: dict[str, object] = {
        "id": next_id("sprint"),
        "number": 1,
        "start_date": date(2026, 9, 3),
        "end_date": date(2026, 9, 7),
        "status": SprintStatus.ACTIVE,
    }
    args.update(overrides)
    return Sprint(**args)  # type: ignore[arg-type]


@pytest.mark.unit
@pytest.mark.parametrize("start", [TODAY, TODAY + timedelta(days=1)], ids=["today", "tomorrow"])
def test_sprint_forward_passes_when_start_is_today_or_later(start: date) -> None:
    validate_sprint_forward(sprint_factory(start_date=start), TODAY)


@pytest.mark.unit
def test_sprint_forward_rejects_retrospective_period_when_v19_creation_breaks() -> None:
    with pytest.raises(SprintWindowError, match="in the past"):
        validate_sprint_forward(sprint_factory(start_date=date(2026, 9, 1)), TODAY)


@pytest.mark.unit
def test_membership_passes_for_once_card_in_active_sprint() -> None:
    validate_task_sprint_membership(task_factory(sprint_id="s1"), sprint_factory())


@pytest.mark.unit
def test_membership_passes_when_every_tick_lies_in_period() -> None:
    card = task_factory(sprint_id="s1", recurrence=OnDates(frozenset({TODAY, date(2026, 9, 7)})))

    validate_task_sprint_membership(card, sprint_factory())


@pytest.mark.unit
def test_membership_rejects_tick_outside_period_and_lists_it() -> None:
    card = task_factory(sprint_id="s1", recurrence=OnDates(frozenset({TODAY, date(2026, 9, 20)})))

    with pytest.raises(SprintMembershipError, match="2026-09-20"):
        validate_task_sprint_membership(card, sprint_factory())


@pytest.mark.unit
@pytest.mark.parametrize(
    "status", [SprintStatus.PLANNED, SprintStatus.COMPLETED], ids=["planned", "completed"]
)
def test_membership_rejects_any_closed_container_when_v28_breaks(status: SprintStatus) -> None:
    card = task_factory(sprint_id="s1", recurrence=Once())

    with pytest.raises(SprintMembershipError, match="not activated"):
        validate_task_sprint_membership(card, sprint_factory(status=status))


@pytest.mark.unit
def test_task_sprint_id_survives_the_serialization_roundtrip() -> None:
    original = task_factory(sprint_id="sprint-77")

    restored = task_from_dict(task_to_dict(original))

    assert restored == original
    assert restored.sprint_id == "sprint-77"
