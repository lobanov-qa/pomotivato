"""Property floor for stats aggregations (spec 04 §8): invariants, not examples.

Only pure functions are fed random rows; DB/clock work stays in @api tests.
pytestmark follows the E1 convention: property suites run in CI explicitly.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pomotivato.services.blocks import WorkBlock
from pomotivato.services.stats import heatmap_rows, streaks

pytestmark = pytest.mark.property

DAY_MIN = date(2026, 1, 1)
DAY_SPAN = 400


@st.composite
def work_blocks(draw, max_items=30):  # fully untyped on purpose: mypy skips pure test helpers
    """Random completed-work blocks scattered over ~13 months."""
    count = draw(st.integers(min_value=0, max_value=max_items))
    blocks = []
    for i in range(count):
        day = DAY_MIN + timedelta(days=draw(st.integers(min_value=0, max_value=DAY_SPAN)))
        minutes = draw(st.integers(min_value=1, max_value=120))
        blocks.append(WorkBlock(f"s-{i}", f"t-{i % 5}", day, minutes))
    return tuple(blocks)


@settings(max_examples=150, deadline=None)
@given(blocks=work_blocks())
def test_streak_current_never_exceeds_record(blocks):
    today = max((b.day for b in blocks), default=DAY_MIN)

    result = streaks(blocks, today=today)

    assert 0 <= result["current"] <= result["record"]


@settings(max_examples=150, deadline=None)
@given(blocks=work_blocks())
def test_heatmap_rows_stay_within_requested_period(blocks):
    start = DAY_MIN + timedelta(days=50)
    end = start + timedelta(days=30)

    rows = heatmap_rows(blocks, start, end)

    dates = {row["date"] for row in rows}
    assert all(row["blocks_done"] >= 1 for row in rows)
    assert all(start.isoformat() <= d <= end.isoformat() for d in dates)


@settings(max_examples=150, deadline=None)
@given(blocks=work_blocks())
def test_streak_record_cannot_exceed_distinct_active_days(blocks):
    days = {b.day for b in blocks}
    today = max(days, default=DAY_MIN)

    result = streaks(blocks, today=today)

    assert result["record"] <= len(days)


@settings(max_examples=150, deadline=None)
@given(
    minutes=st.lists(st.integers(min_value=1, max_value=200), min_size=1, max_size=20),
)
def test_heatmap_focus_min_sums_minutes_of_the_day(minutes):
    day = DAY_MIN
    blocks = tuple(WorkBlock(f"s{i}", "t-1", day, m) for i, m in enumerate(minutes))

    rows = heatmap_rows(blocks, day, day)

    assert rows[0]["focus_min"] == sum(minutes)
    assert rows[0]["blocks_done"] == len(minutes)


@settings(max_examples=50, deadline=None)
@given(today=st.dates(min_value=DAY_MIN, max_value=DAY_MIN + timedelta(days=DAY_SPAN)))
def test_streaks_of_empty_history_are_zero_whenever_today_is(today):
    result = streaks((), today=today)

    assert result["current"] == 0
    assert result["record"] == 0
