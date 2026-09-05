"""Server-Sent Events stream over the session FSM (spec 03 §4).

No event bus in the core (KISS): the stream polls the same honest
``get_view`` a GET would do — catch-up included — and turns a change of
the projection key (state, phase, open segment, closed count) into the
event table of spec 03 §4. A disconnected client costs zero DB writes:
catch-up happens in the generator's own polls while a client is attached.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime

from pomotivato.api.schemas import SessionDto
from pomotivato.core.clock import Clock
from pomotivato.infra.db import Database
from pomotivato.services.session_service import FsmRegistry, SessionService, SessionView

PING_INTERVAL_SEC = 15.0
PING_FRAME = ":ping\n\n"  # SSE comment frame: ignored by clients, seen by proxies
LIVE_STATES = frozenset({"running", "paused"})


def frame(event: str, data: dict[str, object]) -> str:
    """Render one SSE frame: an event name plus a JSON payload line."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def snapshot_data(view: SessionView, now: datetime) -> dict[str, object]:
    """Full session DTO flattened with server_now (clock-skew anchor)."""
    payload: dict[str, object] = SessionDto.from_view(view).model_dump()
    payload["server_now"] = now.isoformat()
    return payload


@dataclass(frozen=True)
class StreamKey:
    """What the client can observe about one view (the diff input)."""

    state: str
    phase: str | None
    open_segment_id: str | None
    ended_count: int


def key_of(view: SessionView) -> StreamKey:
    """Project a session view onto its observable key."""
    open_segment = next((seg for seg in view.timeline if seg.status is None), None)
    ended_count = sum(1 for seg in view.timeline if seg.status is not None)
    return StreamKey(
        state=view.session.state.value,
        phase=view.phase,
        open_segment_id=open_segment.id if open_segment else None,
        ended_count=ended_count,
    )


def diff_events(
    prev: StreamKey, view: SessionView, now: datetime
) -> list[tuple[str, dict[str, object]]]:
    """Translate a key change into spec 03 §4 events (possibly several)."""
    key = key_of(view)
    events: list[tuple[str, dict[str, object]]] = []
    closed = [seg for seg in view.timeline if seg.status is not None]
    for segment in closed[prev.ended_count :]:
        status = segment.status.value if segment.status else None
        events.append(("segment_closed", {"segment_id": segment.id, "status": status}))
    if key.state not in LIVE_STATES:
        events.append(("session_finished", SessionDto.from_view(view).model_dump()))
        return events
    if key.phase != prev.phase or key.open_segment_id != prev.open_segment_id:
        if key.phase is None or key.open_segment_id is None:
            # Live but nothing open (boundary pause): phase_changed would
            # carry nulls, so replay the full honest view instead.
            events.append(("snapshot", snapshot_data(view, now)))
        else:
            events.append(
                (
                    "phase_changed",
                    {
                        "phase": key.phase,
                        "segment_id": key.open_segment_id,
                        "ends_at": view.ends_at.isoformat() if view.ends_at else None,
                        "remaining_sec": view.remaining_sec,
                    },
                )
            )
    elif key.state != prev.state:
        # A pause/resume keeps the same phase: replay the full honest view.
        events.append(("snapshot", snapshot_data(view, now)))
    return events


async def event_stream(
    db: Database,
    clock: Clock,
    registry: FsmRegistry,
    session_id: str,
    first: SessionView,
    poll_sec: float,
    ping_sec: float = PING_INTERVAL_SEC,
) -> AsyncIterator[str]:
    """Yield SSE frames until the session reaches a terminal state.

    The first frame is always ``snapshot``; the last one for a dead (or
    dying) session is always ``session_finished``. Unknown ids raise in
    the router before this generator starts, so a 404 never leaks into
    the stream (spec 03 §4).
    """
    yield frame("snapshot", snapshot_data(first, clock.now()))
    prev = key_of(first)
    if prev.state not in LIVE_STATES:
        yield frame("session_finished", SessionDto.from_view(first).model_dump())
        return
    loop = asyncio.get_running_loop()
    next_ping = loop.time() + ping_sec
    while True:
        if loop.time() >= next_ping:
            next_ping = loop.time() + ping_sec
            yield PING_FRAME
        await asyncio.sleep(poll_sec)
        async with db.new_session() as db_session:
            service = SessionService(db_session, clock, registry)
            view = await service.get_view(session_id)
        key = key_of(view)
        if key != prev:
            for name, data in diff_events(prev, view, clock.now()):
                yield frame(name, data)
            prev = key
            if key.state not in LIVE_STATES:
                return
