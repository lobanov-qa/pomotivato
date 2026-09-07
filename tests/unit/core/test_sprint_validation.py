"""Unit tests for sprint rules V14/V15 (spec 05 §3.10, ADR-0003 p.3)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from pomotivato.core.errors import ValidationError
from pomotivato.core.models import Sprint, SprintStatus
from pomotivato.core.validation import validate_sprint, validate_sprint_transition
from tests.factories.core_models import next_id


def sprint_at(span_days: int, **overrides: object) -> Sprint:
    start = date(2026, 9, 7)
    args: dict[str, object] = {
        "id": next_id("sprint"),
        "number": 1,
        "start_date": start,
        "end_date": start + timedelta(days=span_days - 1),
    }
    args.update(overrides)
    return Sprint(**args)  # type: ignore[arg-type]


@pytest.mark.unit
@pytest.mark.parametrize("span", [1, 7, 14])
def test_sprint_period_within_one_to_fourteen_days_is_valid(span: int) -> None:
    validate_sprint(sprint_at(span))


@pytest.mark.unit
@pytest.mark.parametrize("span", [0, 15])
def test_sprint_period_outside_one_to_fourteen_days_is_rejected(span: int) -> None:
    with pytest.raises(ValidationError, match="1..14 days"):
        validate_sprint(sprint_at(span))


@pytest.mark.unit
def test_sprint_number_must_be_positive() -> None:
    with pytest.raises(ValidationError, match="number"):
        validate_sprint(sprint_at(5, number=0))


@pytest.mark.unit
def test_sprint_text_fields_are_size_capped() -> None:
    with pytest.raises(ValidationError, match="goal exceeds"):
        validate_sprint(sprint_at(5, goal="g" * 201))


@pytest.mark.unit
def test_end_before_start_is_rejected_as_bad_length() -> None:
    start = date(2026, 9, 7)
    with pytest.raises(ValidationError, match="1..14 days"):
        validate_sprint(sprint_at(1, start_date=start, end_date=start - timedelta(days=1)))


@pytest.mark.unit
def test_sprint_transition_allows_only_forward_one_step() -> None:
    validate_sprint_transition(SprintStatus.PLANNED, SprintStatus.ACTIVE)
    validate_sprint_transition(SprintStatus.ACTIVE, SprintStatus.COMPLETED)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("old", "new"),
    [
        (SprintStatus.PLANNED, SprintStatus.COMPLETED),
        (SprintStatus.ACTIVE, SprintStatus.PLANNED),
        (SprintStatus.COMPLETED, SprintStatus.ACTIVE),
        (SprintStatus.COMPLETED, SprintStatus.PLANNED),
        (SprintStatus.ACTIVE, SprintStatus.ACTIVE),
    ],
)
def test_sprint_transition_refuses_shortcuts_and_reopens(
    old: SprintStatus, new: SprintStatus
) -> None:
    with pytest.raises(ValidationError, match="transition"):
        validate_sprint_transition(old, new)
