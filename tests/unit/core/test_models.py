"""Unit tests for core models and serialization round-trip (spec 01 §2)."""

from __future__ import annotations

from datetime import date

import pytest

from pomotivato.core.errors import ValidationError
from pomotivato.core.models import (
    Daily,
    Once,
    WeeklyCount,
    WeeklyDays,
    day_plan_from_dict,
    recurrence_from_dict,
    repetition_state_from_dict,
    review_from_dict,
    segment_from_dict,
    session_from_dict,
    session_settings_from_dict,
    task_from_dict,
    task_to_dict,
    to_dict,
)
from tests.factories.core_models import (
    day_plan_factory,
    repetition_factory,
    review_factory,
    segment_factory,
    session_factory,
    settings_factory,
    slot_factory,
    task_factory,
)

ROUND_TRIP_CASES = [
    ("task", lambda: task_factory(), task_from_dict, task_to_dict),
    (
        "task-study",
        lambda: task_factory(type="study", when_then="if Slack opens, first docs"),
        task_from_dict,
        task_to_dict,
    ),
    ("session", session_factory, session_from_dict, to_dict),
    ("segment", segment_factory, segment_from_dict, to_dict),
    (
        "segment-finished",
        lambda: segment_factory(task_id="t1", status="completed"),
        segment_from_dict,
        to_dict,
    ),
    ("review", review_factory, review_from_dict, to_dict),
    ("plan", day_plan_factory, day_plan_from_dict, to_dict),
    ("settings", settings_factory, session_settings_from_dict, to_dict),
    ("repetition", repetition_factory, repetition_state_from_dict, to_dict),
]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("name", "build", "parse", "dump"),
    ROUND_TRIP_CASES,
    ids=[case[0] for case in ROUND_TRIP_CASES],
)
def test_model_round_trips_when_serialized_and_parsed(name, build, parse, dump):
    original = build()

    restored = parse(dump(original))

    assert restored == original, name


@pytest.mark.unit
@pytest.mark.parametrize(
    "recurrence",
    [Once(), Daily(), WeeklyDays(frozenset({0, 4})), WeeklyCount(n=3, start=date(2026, 9, 2))],
    ids=["once", "daily", "weekly_days", "weekly_count"],
)
def test_recurrence_round_trips_when_serialized_with_kind_tag(recurrence):
    data = task_to_dict(task_factory(recurrence=recurrence))["recurrence"]

    restored = recurrence_from_dict(data)

    assert restored == recurrence


@pytest.mark.unit
@pytest.mark.parametrize("missing", ["id", "title", "type", "recurrence", "created_at"])
def test_task_from_dict_raises_when_required_field_missing(missing):
    data = task_to_dict(task_factory())
    del data[missing]

    with pytest.raises(ValidationError, match=f"missing field '{missing}'"):
        task_from_dict(data)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("field", "value", "message"),
    [("type", "quantum", "unknown type"), ("status", "nope", "unknown status")],
)
def test_task_from_dict_raises_when_enum_value_unknown(field, value, message):
    data = task_to_dict(task_factory())
    data[field] = value

    with pytest.raises(ValidationError, match=message):
        task_from_dict(data)


@pytest.mark.unit
def test_task_from_dict_raises_when_recurrence_kind_unknown():
    data = task_to_dict(task_factory())
    data["recurrence"] = {"kind": "monthly"}

    with pytest.raises(ValidationError, match="unknown recurrence kind"):
        task_from_dict(data)


@pytest.mark.unit
def test_task_from_dict_raises_when_datetime_naive():
    data = task_to_dict(task_factory())
    data["created_at"] = "2026-09-03T09:00:00"

    with pytest.raises(ValidationError, match="naive datetime rejected"):
        task_from_dict(data)


@pytest.mark.unit
def test_models_are_frozen_when_mutated():
    targets = [
        (task_factory(), "title", "hacked"),
        (settings_factory(), "work_min", 999),
        (slot_factory(), "sector", 99),
        (review_factory(), "score", 1),
    ]

    for obj, attr, value in targets:
        with pytest.raises(Exception, match="cannot assign|immutable|frozen|read-only"):
            setattr(obj, attr, value)


@pytest.mark.unit
def test_weekly_count_parses_start_as_iso_date_when_from_dict():
    payload = {"kind": "weekly_count", "n": 2, "start": "2026-09-07"}

    parsed = recurrence_from_dict(payload)

    assert parsed == WeeklyCount(n=2, start=date(2026, 9, 7))
