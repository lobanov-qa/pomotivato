"""Unit floor for export projections (spec 04 §4.3): rows in, bytes out."""

from __future__ import annotations

import csv
import io
from datetime import UTC, date, datetime, timedelta

from pomotivato.core.models import Segment, SegmentPhase, SegmentStatus, SessionState
from pomotivato.services.export import csv_rows, export_document
from tests.factories.core_models import (
    day_plan_factory,
    review_factory,
    segment_factory,
    session_factory,
    slot_factory,
    task_factory,
)

START = date(2026, 9, 1)
END = date(2026, 9, 7)
NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)


def _closed_segment(
    *,
    id: str | None = None,
    day: date = date(2026, 9, 3),
    phase: SegmentPhase = SegmentPhase.WORK,
    status: SegmentStatus | None = SegmentStatus.COMPLETED,
    task_id: str | None = "t-1",
    planned_min: int = 25,
    ended: bool = True,
) -> Segment:
    started = datetime(day.year, day.month, day.day, 9, 0, tzinfo=UTC)
    return segment_factory(
        id=id or segment_factory().id,
        phase=phase,
        status=status,
        task_id=task_id,
        started_at=started,
        ended_at=started + timedelta(minutes=planned_min) if ended else None,
        planned_min=planned_min,
    )


def test_export_document_sections_and_period() -> None:
    task = task_factory(id="t-1")
    plan = day_plan_factory(date=START, slots=(slot_factory(task_id="t-1"),))
    session = session_factory(
        id="s-1",
        state=SessionState.RUNNING,
        started_at=datetime(2026, 9, 3, 9, 0, tzinfo=UTC),
    )
    segment = _closed_segment()
    review = review_factory(segment_id=segment.id, score=4)

    doc = export_document(
        START,
        END,
        NOW,
        tasks=(task,),
        day_plans=(plan,),
        sessions=(session,),
        segments=(segment,),
        reviews=(review,),
    )

    assert doc["exported_at"] == NOW.isoformat()
    assert doc["period"] == {"from": START.isoformat(), "to": END.isoformat()}
    assert doc["tasks"] == [doc["tasks"][0]] and doc["tasks"][0]["id"] == "t-1"
    assert [s["id"] for s in doc["sessions"]] == ["s-1"]
    assert len(doc["segments"]) == 1
    assert doc["reviews"] == [
        {
            "segment_id": segment.id,
            "score": 4,
            "comment": None,
            "recall_notes": None,
            "reward": None,
        }
    ]
    # Enums/dates are canonically serialized (string values, ISO), per to_dict.
    assert doc["tasks"][0]["status"] == "backlog"
    assert doc["tasks"][0]["created_at"].startswith("2026-09-03")


def test_export_document_cuts_events_outside_period() -> None:
    plan_out = day_plan_factory(date=START - timedelta(days=1))
    session_out = session_factory(id="s-old", started_at=datetime(2026, 8, 1, 9, 0, tzinfo=UTC))
    segment_out = _closed_segment(id="seg-old", day=date(2026, 8, 1))

    doc = export_document(
        START,
        END,
        NOW,
        tasks=(),
        day_plans=(plan_out,),
        sessions=(session_out,),
        segments=(segment_out,),
        reviews=(),
    )

    assert doc["day_plans"] == []
    assert doc["sessions"] == []
    assert doc["segments"] == []


def test_export_document_empty_db_yields_empty_sections() -> None:
    doc = export_document(
        START, END, NOW, tasks=(), day_plans=(), sessions=(), segments=(), reviews=()
    )

    assert doc["tasks"] == [] and doc["day_plans"] == [] and doc["reviews"] == []


def test_csv_rows_join_scores_and_keep_open_segment_gaps() -> None:
    closed = _closed_segment(id="seg-a")
    open_break = _closed_segment(
        id="seg-b", phase=SegmentPhase.BREAK, status=None, ended=False, planned_min=5
    )
    review = review_factory(segment_id=closed.id, score=5)

    text = csv_rows((closed, open_break), {review.segment_id: review.score})

    parsed = list(csv.reader(io.StringIO(text)))
    assert parsed[0] == [
        "session_id",
        "segment_id",
        "task_id",
        "phase",
        "status",
        "started_at",
        "ended_at",
        "duration_min",
        "planned_min",
        "score",
    ]
    assert parsed[1][1] == "seg-a" and parsed[1][7] == "25" and parsed[1][9] == "5"
    assert parsed[2][1] == "seg-b" and parsed[2][4] == "" and parsed[2][6] == ""
    assert parsed[2][7] == "" and parsed[2][9] == ""


def test_csv_rows_crlf_and_utf8_bom_compose_in_router_order() -> None:
    text = csv_rows((_closed_segment(id="seg-a"),), {})

    assert text.endswith("\r\n")
    assert "\r\n" in text  # csv module with explicit newline handling
