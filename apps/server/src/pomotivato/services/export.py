"""Raw data export for GET /api/export (spec 04 §4.3).

`export_document`/`csv_rows` are pure over loaded rows (same discipline as
daily_summary/stats); `ExportService` is the reading glue. JSON reuses the
canonical core `to_dict` — export and persistence never drift. CSV carries
segments with their reviews joined as one table (the user's spreadsheet
format); duration is the wall-minute formula shared with blocks.py.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from pomotivato.core.models import DayPlan, Review, Segment, Session, Task, to_dict
from pomotivato.infra.repository import DayPlanRepository, TaskRepository
from pomotivato.infra.repository_sessions import (
    ReviewRepository,
    SegmentRepository,
    SessionRepository,
)
from pomotivato.services.stats_service import _validate_period

CSV_HEADER = (
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
)


def export_document(
    start: date,
    end: date,
    now: datetime,
    *,
    tasks: tuple[Task, ...],
    day_plans: tuple[DayPlan, ...],
    sessions: tuple[Session, ...],
    segments: tuple[Segment, ...],
    reviews: tuple[Review, ...],
) -> dict[str, Any]:
    """Assemble the JSON document (events cut by period, tasks in full)."""

    def in_period(moment: datetime | None) -> bool:
        return moment is not None and start <= moment.date() <= end

    events = {
        "day_plans": [to_dict(plan) for plan in day_plans if start <= plan.date <= end],
        "sessions": [to_dict(s) for s in sessions if in_period(s.started_at)],
        "segments": [to_dict(s) for s in segments if in_period(s.started_at)],
        "reviews": [to_dict(r) for r in reviews],  # joined per segment below
    }
    segment_ids = {segment["id"] for segment in events["segments"]}
    events["reviews"] = [
        review for review in events["reviews"] if review["segment_id"] in segment_ids
    ]
    return {
        "exported_at": now.isoformat(),
        "period": {"from": start.isoformat(), "to": end.isoformat()},
        "tasks": [to_dict(t) for t in tasks],
        **events,
    }


def csv_rows(segments: tuple[Segment, ...], scores: dict[str, int]) -> str:
    """One CSV table: segments joined with review scores, CRLF per spec."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(CSV_HEADER)
    for segment in segments:
        duration = (
            round((segment.ended_at - segment.started_at).total_seconds() / 60)
            if segment.started_at and segment.ended_at
            else ""
        )
        writer.writerow(
            [
                segment.session_id,
                segment.id,
                segment.task_id or "",
                segment.phase.value,
                segment.status.value if segment.status else "",
                segment.started_at.isoformat() if segment.started_at else "",
                segment.ended_at.isoformat() if segment.ended_at else "",
                duration,
                segment.planned_min,
                scores.get(segment.id, ""),
            ]
        )
    return buffer.getvalue()


class ExportService:
    """Load all rows once and hand them to the pure projections."""

    def __init__(self, session: AsyncSession) -> None:
        self._tasks = TaskRepository(session)
        self._plans = DayPlanRepository(session)
        self._sessions = SessionRepository(session)
        self._segments = SegmentRepository(session)
        self._reviews = ReviewRepository(session)

    async def gather(
        self, start: date, end: date, now: datetime
    ) -> tuple[tuple[Segment, ...], dict[str, int], dict[str, Any]]:
        """Period-cut segments (CSV truth) + full JSON document.

        Both formats share one row load and one period semantics (§4.3):
        events cut by started_at/date, reviews by owning segment, tasks
        always the full catalog.
        """
        _validate_period(start, end)
        segments: list[Segment] = []
        reviews: list[Review] = []
        for model in await self._sessions.list_all():
            segments += list(await self._segments.get_many_for_session(model.id))
            reviews += list(await self._reviews.get_many_for_session(model.id))
        scores = {review.segment_id: review.score for review in reviews}

        def in_period(segment: Segment) -> bool:
            return segment.started_at is not None and start <= segment.started_at.date() <= end

        period_segments = tuple(segment for segment in segments if in_period(segment))
        document = export_document(
            start,
            end,
            now,
            tasks=await self._tasks.list_all(),
            day_plans=await self._plans.list_all(),
            sessions=await self._sessions.list_all(),
            segments=tuple(segments),
            reviews=tuple(reviews),
        )
        return period_segments, scores, document


def json_bytes(document: dict[str, Any]) -> bytes:
    """UTF-8 JSON bytes; sort_keys keeps the file diffable across runs."""
    return json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def csv_bytes(segments: tuple[Segment, ...], scores: dict[str, int]) -> bytes:
    """utf-8-sig (BOM per spec ⚑ Q7): Excel opens Cyrillic without dancing."""
    return csv_rows(segments, scores).encode("utf-8-sig")


CSV_MEDIA = "text/csv; charset=utf-8"
