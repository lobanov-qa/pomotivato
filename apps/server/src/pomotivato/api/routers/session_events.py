"""SSE door for one session (spec 03 §4), mounted on the sessions router.

Kept separate from sessions.py so that file stays one-responsibility
(commands) while this one is (read-only streaming). The initial view is
read in its own committed transaction, NOT the request-scoped one: a
stream lives for minutes, and an uncommitted write from the request
session would lock the single-writer SQLite for its whole lifetime.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from pomotivato.api.deps import ClockDep, DatabaseDep, RegistryDep
from pomotivato.api.sse import PING_INTERVAL_SEC, event_stream
from pomotivato.infra.db import Database
from pomotivato.services.session_service import SessionService, SessionView

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    # nginx and friends must not buffer the stream into one big response
    "X-Accel-Buffering": "no",
}


@router.get("/{session_id}/events")
async def session_events(
    session_id: str,
    request: Request,
    clock: ClockDep,
    registry: RegistryDep,
    db: DatabaseDep,
) -> StreamingResponse:
    """Stream phase transitions of one session until it dies (spec 03 §4).

    404/409 are raised here, before the body starts, so error responses
    keep the JSON envelope instead of a fake event stream.
    """
    first: SessionView = await _initial_view(db, clock, registry, session_id)
    poll_sec: float = getattr(request.app.state, "sse_poll_interval_sec", 1.0)
    ping_sec: float = getattr(request.app.state, "sse_ping_interval_sec", PING_INTERVAL_SEC)
    return StreamingResponse(
        event_stream(db, clock, registry, session_id, first, poll_sec, ping_sec),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


async def _initial_view(
    db: Database, clock: ClockDep, registry: RegistryDep, session_id: str
) -> SessionView:
    """Catch-up read in a short-lived transaction that commits immediately."""
    async with db.new_session() as session:
        return await SessionService(session, clock, registry).get_view(session_id)
