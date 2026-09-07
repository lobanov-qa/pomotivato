"""Unit floor for pure stats helpers (spec 04 §3): no DB, no clock lies."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from pomotivato.core.models import Review, Segment, SegmentPhase, SegmentStatus, TaskStatus
from pomotivato.services.blocks import WorkBlock, completed_work_blocks
from pomotivato.services.stats import (
    estimate_vs_fact,
    goal_depth,
    heatmap_rows,
    parent_progress,
    quadrant_stats,
    streaks,
    zombies,
)
from tests.factories.core_models import review_factory, segment_factory, task_factory

MONDAY = date(2026, 9, 7)


def _dt(day: date, hour: int = 9) -> datetime:
    return datetime(day.year, day.month, day.day, hour, tzinfo=UTC)


def work_block(
    task_id: str = "t-1", day: date = MONDAY, minutes: int = 25, **overrides: Any
) -> Segment:
    """A completed WORK segment on `day` lasting `minutes`."""
    started = _dt(day)
    args: dict[str, Any] = {
        "phase": SegmentPhase.WORK,
        "status": SegmentStatus.COMPLETED,
        "task_id": task_id,
        "started_at": started,
        "ended_at": started + timedelta(minutes=minutes),
        "planned_min": minutes,
    }
    args.update(overrides)
    return segment_factory(**args)


def review_for(block: Segment, score: int = 4) -> Review:
    return review_factory(segment_id=block.id, score=score)


class TestCompletedWorkBlocks:
    def test_keeps_only_completed_work_segments(self) -> None:
        done = work_block(day=MONDAY)
        break_seg = work_block(phase=SegmentPhase.BREAK)
        interrupted = work_block(status=SegmentStatus.INTERRUPTED)
        open_seg = work_block(status=None, ended_at=None)

        blocks = completed_work_blocks((done, break_seg, interrupted, open_seg))

        assert [b.segment_id for b in blocks] == [done.id]

    def test_block_carries_day_minutes_and_task(self) -> None:
        done = work_block(task_id="t-9", day=MONDAY, minutes=10)

        block = completed_work_blocks((done,))[0]

        assert block == WorkBlock(
            segment_id=done.id,
            task_id="t-9",
            day=MONDAY,
            minutes=10,
        )


class TestHeatmap:
    def test_groups_blocks_by_day_within_period(self) -> None:
        blocks = (
            WorkBlock("s1", "t-1", MONDAY, 25),
            WorkBlock("s2", "t-1", MONDAY, 25),
            WorkBlock("s3", "t-2", MONDAY + timedelta(days=1), 10),
        )

        rows = heatmap_rows(blocks, MONDAY, MONDAY + timedelta(days=1))

        assert rows == [
            {"date": MONDAY.isoformat(), "blocks_done": 2, "focus_min": 50},
            {"date": (MONDAY + timedelta(days=1)).isoformat(), "blocks_done": 1, "focus_min": 10},
        ]

    def test_days_without_blocks_do_not_appear(self) -> None:
        rows = heatmap_rows(
            (WorkBlock("s1", "t-1", MONDAY, 25),), MONDAY, MONDAY + timedelta(days=3)
        )

        assert [r["date"] for r in rows] == [MONDAY.isoformat()]


class TestStreaks:
    def test_counts_consecutive_days_with_blocks(self) -> None:
        days = [MONDAY - timedelta(days=2), MONDAY - timedelta(days=1), MONDAY]
        blocks = tuple(WorkBlock(f"s{i}", "t-1", d, 25) for i, d in enumerate(days))

        result = streaks(blocks, today=MONDAY)

        assert result["current"] == 3
        assert result["current_started"] == days[0].isoformat()

    def test_grace_keeps_today_empty_from_breaking_yesterday_chain(self) -> None:
        blocks = (WorkBlock("s1", "t-1", MONDAY - timedelta(days=1), 25),)

        result = streaks(blocks, today=MONDAY)

        assert result["current"] == 1
        assert result["record"] == 1

    def test_current_is_zero_when_yesterday_also_empty(self) -> None:
        blocks = (WorkBlock("s1", "t-1", MONDAY - timedelta(days=3), 25),)

        result = streaks(blocks, today=MONDAY)

        assert result["current"] == 0
        assert result["record"] == 1

    def test_record_spans_gap_between_chains(self) -> None:
        days = [
            MONDAY - timedelta(days=6),
            MONDAY - timedelta(days=5),
            MONDAY - timedelta(days=4),
            MONDAY - timedelta(days=1),
            MONDAY,
        ]
        blocks = tuple(WorkBlock(f"s{i}", "t-1", d, 25) for i, d in enumerate(days))

        result = streaks(blocks, today=MONDAY)

        assert result["current"] == 2
        assert result["record"] == 3
        assert result["record_started"] == days[0].isoformat()

    def test_empty_history_returns_zeroes(self) -> None:
        result = streaks((), today=MONDAY)

        assert result == {
            "current": 0,
            "current_started": None,
            "record": 0,
            "record_started": None,
        }


class TestEstimateVsFact:
    def test_ratio_is_actual_over_estimate_over_matched_tasks(self) -> None:
        planned = task_factory(id="t-1", status=TaskStatus.DONE, estimate_blocks=2)
        segs = (work_block("t-1"), work_block("t-1"), work_block("t-1"))

        result = estimate_vs_fact((planned,), completed_work_blocks(segs))

        assert result["ratio"] == 1.5
        assert result["points"] == [
            {"task_id": "t-1", "title": planned.title, "estimate": 2, "actual": 3}
        ]

    def test_excludes_done_task_without_actual_blocks(self) -> None:
        orphan = task_factory(id="t-2", status=TaskStatus.DONE, estimate_blocks=4)

        result = estimate_vs_fact((orphan,), ())

        assert result["ratio"] is None
        assert result["points"] == []

    def test_excludes_not_done_tasks(self) -> None:
        backlog = task_factory(id="t-3", status=TaskStatus.BACKLOG, estimate_blocks=2)
        segs = (work_block("t-3"), work_block("t-3"))

        result = estimate_vs_fact((backlog,), completed_work_blocks(segs))

        assert result["ratio"] is None


class TestQuadrants:
    def test_buckets_tasks_by_important_and_urgent(self) -> None:
        q1 = task_factory(id="t-1", important=True, urgent=True, status=TaskStatus.DONE)
        q2 = task_factory(id="t-2", important=True, urgent=False, status=TaskStatus.DONE)
        q3 = task_factory(id="t-3", important=False, urgent=True, status=TaskStatus.DONE)
        q4 = task_factory(id="t-4", important=False, urgent=False, status=TaskStatus.DONE)
        segs = tuple(work_block(t.id) for t in (q1, q2, q3, q4))
        blocks = completed_work_blocks(segs)
        reviews = tuple(review_for(seg, score=i + 1) for i, seg in enumerate(segs))

        rows = quadrant_stats((q1, q2, q3, q4), blocks, reviews)

        by_key = {r["key"]: r for r in rows}
        assert by_key["important_urgent"]["tasks_done"] == 1
        assert by_key["important_urgent"]["blocks"] == 1
        assert by_key["important_urgent"]["average_score"] == 1.0
        assert by_key["neither"]["average_score"] == 4.0

    def test_quadrant_without_tasks_still_reports_zero_row(self) -> None:
        rows = quadrant_stats((), (), ())

        assert {r["key"] for r in rows} == {
            "important_urgent",
            "important_not_urgent",
            "urgent_not_important",
            "neither",
        }
        assert all(r["tasks_done"] == 0 for r in rows)


class TestGoalDepth:
    @pytest.mark.parametrize("filled", [0, 1, 2, 3])
    def test_counts_tasks_by_number_of_scientific_fields(self, filled: int) -> None:
        fields = ["done_criteria", "benefit", "when_then"][:filled]
        task = task_factory(
            status=TaskStatus.DONE, **{f: f"value-{i}" for i, f in enumerate(fields)}
        )

        rows = goal_depth((task,))

        assert [r["tasks"] for r in rows] == [1 if i == filled else 0 for i in range(4)]
        assert rows[filled]["done_ratio"] == 1.0

    def test_archived_tasks_excluded_from_sample(self) -> None:
        archived = task_factory(status=TaskStatus.ARCHIVED)

        rows = goal_depth((archived,))

        assert sum(r["tasks"] for r in rows) == 0


class TestParentProgress:
    def test_reports_done_over_total_children(self) -> None:
        parent = task_factory(id="p-1")
        done = task_factory(id="c-1", parent_id="p-1", status=TaskStatus.DONE)
        open_child = task_factory(id="c-2", parent_id="p-1", status=TaskStatus.DOING)

        rows = parent_progress((parent, done, open_child))

        assert rows == [
            {"task_id": "p-1", "title": parent.title, "done_children": 1, "total_children": 2}
        ]

    def test_no_children_means_no_rows(self) -> None:
        lone = task_factory()

        assert parent_progress((lone,)) == []

    def test_child_of_deleted_parent_is_skipped(self) -> None:
        ghost_child = task_factory(id="c-1", parent_id="gone", status=TaskStatus.DONE)

        assert parent_progress((ghost_child,)) == []


class TestZombies:
    def test_flags_doing_task_idle_beyond_threshold(self) -> None:
        stuck = task_factory(id="t-1", status=TaskStatus.DOING)
        last_done = completed_work_blocks((work_block("t-1", day=MONDAY - timedelta(days=5)),))
        now = _dt(MONDAY, hour=18)

        result = zombies((stuck,), last_done, now=now, threshold_days=3)

        assert result["count"] == 1
        assert result["items"] == [{"task_id": "t-1", "title": stuck.title, "days_stuck": 5}]

    def test_recent_block_keeps_task_alive(self) -> None:
        alive = task_factory(id="t-1", status=TaskStatus.DOING)
        recent = completed_work_blocks((work_block("t-1", day=MONDAY - timedelta(days=1)),))

        result = zombies((alive,), recent, now=_dt(MONDAY), threshold_days=3)

        assert result == {"count": 0, "items": []}

    def test_doing_task_without_blocks_falls_back_to_created_at(self) -> None:
        fresh = task_factory(
            id="t-1", status=TaskStatus.DOING, created_at=_dt(MONDAY) - timedelta(days=10)
        )

        result = zombies((fresh,), (), now=_dt(MONDAY), threshold_days=3)

        assert result["count"] == 1
        assert result["items"][0]["days_stuck"] == 10

    def test_ignores_statuses_other_than_doing(self) -> None:
        planned = task_factory(
            id="t-1", status=TaskStatus.PLANNED, created_at=_dt(MONDAY) - timedelta(days=10)
        )

        assert zombies((planned,), (), now=_dt(MONDAY), threshold_days=3)["count"] == 0
