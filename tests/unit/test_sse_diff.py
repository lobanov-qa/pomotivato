"""Unit floor for the SSE projection: key diffing and frame rendering.

The generator itself is covered at @api level; here every pure helper of
api/sse.py is tested without HTTP or DB (spec 03 §4, §9).
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta

import pytest

from pomotivato.api.sse import (
    PING_FRAME,
    StreamKey,
    diff_events,
    frame,
    key_of,
    snapshot_data,
)
from pomotivato.core.models import (
    Review,
    Segment,
    SegmentPhase,
    SegmentStatus,
    SessionState,
)
from pomotivato.services.session_service import SessionView
from tests.factories.core_models import (
    DEFAULT_MOMENT,
    review_factory,
    segment_factory,
    session_factory,
)

ENDED = DEFAULT_MOMENT + timedelta(minutes=10)


def _view(
    state: SessionState = SessionState.RUNNING,
    phase: SegmentPhase | None = SegmentPhase.WORK,
    segments: tuple[Segment, ...] = (),
    reviews: tuple[Review, ...] = (),
) -> SessionView:
    return SessionView(
        session=session_factory(state=state),
        phase=phase.value if phase else None,
        remaining_sec=600,
        ends_at=ENDED,
        timeline=segments,
        reviews=reviews,
        average_score=None,
    )


def _seg(session_id: str, **overrides: object) -> Segment:
    return segment_factory(session_id=session_id, started_at=DEFAULT_MOMENT, **overrides)


@pytest.mark.unit
def test_key_of_counts_open_and_ended_segments_when_timeline_mixed():
    base = _view()
    ended = _seg(base.session.id, status=SegmentStatus.COMPLETED, ended_at=ENDED)
    open_seg = _seg(base.session.id)
    view = _view(segments=(ended, open_seg))

    key = key_of(view)

    assert key == StreamKey("running", "work", open_seg.id, 1)


@pytest.mark.unit
def test_key_of_has_no_open_segment_when_session_idle():
    key = key_of(_view(state=SessionState.STOPPED, phase=None))

    assert key.open_segment_id is None
    assert key.ended_count == 0


@pytest.mark.unit
def test_diff_events_reports_closed_segment_before_phase_change_when_work_ends():
    base = _view()
    work_open = _seg(base.session.id)
    rest = _seg(base.session.id, phase=SegmentPhase.BREAK)
    before = _view(segments=(work_open,))
    work_done = replace(work_open, status=SegmentStatus.COMPLETED, ended_at=ENDED)
    after = _view(phase=SegmentPhase.BREAK, segments=(work_done, rest))

    events = diff_events(key_of(before), after, DEFAULT_MOMENT)

    assert [name for name, _ in events] == ["segment_closed", "phase_changed"]
    assert events[0][1] == {"segment_id": work_done.id, "status": "completed"}
    assert events[1][1]["phase"] == "break"
    assert events[1][1]["segment_id"] == rest.id


@pytest.mark.unit
def test_diff_events_ends_with_session_finished_when_state_terminal():
    base = _view()
    work = _seg(base.session.id, status=SegmentStatus.COMPLETED, ended_at=ENDED)
    break_seg = _seg(base.session.id, phase=SegmentPhase.BREAK)
    before = _view(phase=SegmentPhase.BREAK, segments=(work, break_seg))
    stopped = _seg(
        base.session.id,
        phase=SegmentPhase.BREAK,
        status=SegmentStatus.INTERRUPTED,
        ended_at=ENDED,
    )
    after = _view(state=SessionState.STOPPED, phase=None, segments=(work, stopped))

    events = diff_events(key_of(before), after, DEFAULT_MOMENT)

    assert [name for name, _ in events] == ["segment_closed", "session_finished"]
    assert events[0][1] == {"segment_id": stopped.id, "status": "interrupted"}
    assert events[1][1]["state"] == "stopped"


@pytest.mark.unit
def test_diff_events_replays_snapshot_when_only_state_changed_within_phase():
    view = _view()
    paused = _view(state=SessionState.PAUSED, segments=view.timeline)

    events = diff_events(key_of(view), paused, DEFAULT_MOMENT)

    assert [name for name, _ in events] == ["snapshot"]
    assert events[0][1]["state"] == "paused"


@pytest.mark.unit
def test_diff_events_replays_snapshot_instead_of_null_phase_when_boundary_pause():
    base = _view()
    work = _seg(base.session.id, status=SegmentStatus.COMPLETED, ended_at=ENDED)
    before = _view(segments=(work,))
    # auto_start_next=False crossed the deadline: live, nothing open, no phase
    boundary = _view(state=SessionState.PAUSED, phase=None, segments=(work,))

    events = diff_events(key_of(before), boundary, DEFAULT_MOMENT)

    assert [name for name, _ in events] == ["snapshot"]
    assert events[0][1]["phase"] is None


@pytest.mark.unit
def test_diff_events_is_silent_when_projection_key_unchanged():
    view = _view()

    assert diff_events(key_of(view), _view(), DEFAULT_MOMENT) == []


@pytest.mark.unit
def test_frame_renders_event_name_and_json_data_line():
    text = frame("phase_changed", {"phase": "work"})

    assert text == 'event: phase_changed\ndata: {"phase": "work"}\n\n'


@pytest.mark.unit
def test_snapshot_data_flattens_dto_with_server_now():
    view = _view(reviews=(review_factory(score=4), review_factory(score=5)))

    payload = snapshot_data(view, DEFAULT_MOMENT)

    assert payload["server_now"] == DEFAULT_MOMENT.isoformat()
    assert payload["id"] == view.session.id
    json.dumps(payload)  # SSE data must always be serializable


@pytest.mark.unit
def test_ping_frame_is_sse_comment_with_blank_line():
    # Clients ignore ":" lines; proxies count them as traffic (spec 03 §4).
    assert PING_FRAME == ":ping\n\n"
