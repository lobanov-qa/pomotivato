"""HTTP floor for GET /api/sessions/{id}/events (spec 03 §4, §9).

httpx.ASGITransport buffers the whole body before returning it, which is
structurally blind to an endless stream -- so these tests speak the raw
ASGI HTTP protocol: each ``http.response.body`` message is a chunk as the
generator yields it. Poll interval drops to ~1 ms via app.state while
FakeClock jumps minutes, so transitions land instantly (no sleeps).
Every frame await is timeout-guarded: a regression fails, never hangs.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Iterator, MutableMapping
from datetime import timedelta
from http import HTTPStatus
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI

from pomotivato.api.sse import PING_FRAME, PING_INTERVAL_SEC
from pomotivato.core.clock import FakeClock
from pomotivato.infra.migrations import upgrade_db
from pomotivato.main import create_app
from tests.factories.core_models import DEFAULT_MOMENT

FAST = {
    "work_min": 10,
    "break_min": 5,
    "long_break_min": 15,
    "long_break_every": 2,
    "auto_start_next": True,
}
FRAME_TIMEOUT_SEC = 5.0


@pytest.fixture
def sse_app(tmp_path: Path) -> Iterator[tuple[FastAPI, FakeClock]]:
    """App over temp DB + frozen clock + fast polls (schema pre-upgraded)."""
    db_path = tmp_path / "sse-test.db"
    upgrade_db(db_path)
    app = create_app(db_path)
    app.state.sse_poll_interval_sec = 0.001
    app.state.sse_ping_interval_sec = 3600.0  # keepalive timing tested separately
    clock = FakeClock(DEFAULT_MOMENT)
    app.state.clock = clock
    yield app, clock


def _scope(method: str, path: str, body: bytes) -> dict[str, Any]:
    headers = [(b"host", b"test"), (b"content-length", str(len(body)).encode())]
    if body:
        headers.append((b"content-type", b"application/json"))
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "client": ("test", 123),
        "server": ("test", 80),
        "headers": headers,
    }


async def _request(
    app: FastAPI, method: str, path: str, body: dict[str, Any] | None = None
) -> tuple[int, bytes, dict[bytes, bytes]]:
    """One complete request-response round trip over the ASGI protocol."""
    payload = b"" if body is None else json.dumps(body).encode()

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": payload, "more_body": False}

    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def send(message: MutableMapping[str, Any]) -> None:
        queue.put_nowait(dict(message))

    await app(_scope(method, path, payload), receive, send)
    start = await queue.get()
    assert start["type"] == "http.response.start"
    chunks = b""
    while True:
        message = await queue.get()
        assert message["type"] == "http.response.body"
        chunks += message.get("body", b"")
        if not message.get("more_body"):
            break
    headers = {k.lower(): v for k, v in start["headers"]}
    status: int = start["status"]
    return status, chunks, headers


class _Stream:
    """A live SSE connection: ASGI messages arrive as the generator yields."""

    def __init__(self, app: FastAPI, path: str) -> None:
        self._app = app
        self._path = path
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._closed = False
        self._task: asyncio.Task[None] | None = None
        self._text = ""
        self.status = -1
        self.headers: dict[bytes, bytes] = {}

    async def _receive(self) -> dict[str, Any]:
        while True:
            await asyncio.sleep(0.02)
            if self._closed:
                return {"type": "http.disconnect"}
        # unreachable: the loop only exits via the return above

    async def _send(self, message: MutableMapping[str, Any]) -> None:
        self._queue.put_nowait(dict(message))

    async def __aenter__(self) -> _Stream:
        self._task = asyncio.create_task(
            self._app(_scope("GET", self._path, b""), self._receive, self._send)
        )
        start = await asyncio.wait_for(self._queue.get(), FRAME_TIMEOUT_SEC)
        assert start["type"] == "http.response.start", start
        self.status = start["status"]
        self.headers = {k.lower(): v for k, v in start["headers"]}
        return self

    async def __aexit__(self, *exc: object) -> None:
        self._closed = True
        if self._task is not None and not self._task.done():
            self._task.cancel()
        assert self._task is not None
        with contextlib.suppress(asyncio.CancelledError):
            await self._task

    async def _pump(self) -> None:
        """Move one ASGI body message into the text buffer (timeout-guarded)."""
        message = await asyncio.wait_for(self._queue.get(), FRAME_TIMEOUT_SEC)
        assert message["type"] == "http.response.body", message
        self._text += message.get("body", b"").decode()

    async def next_event(self) -> tuple[str, dict[str, Any]]:
        """Await the next complete SSE frame; comment frames (pings) skipped."""
        while True:
            while "\n\n" not in self._text:
                await self._pump()
            block, self._text = self._text.split("\n\n", 1)
            if block.startswith(":"):
                continue
            lines = block.splitlines()
            name = next(line[7:] for line in lines if line.startswith("event: "))
            data_line = next(line[6:] for line in lines if line.startswith("data: "))
            return name, json.loads(data_line)

    async def raw_until(self, needle: str) -> str:
        """Accumulate raw text until needle appears; guards runaway output."""
        for _ in range(2000):
            if needle in self._text:
                return self._text
            await self._pump()
        raise AssertionError(f"{needle!r} never arrived; got {self._text[:200]!r}")


async def _start_session(app: FastAPI) -> str:
    """Seed two tasks + a plan + a live session; return its id."""
    t1 = await _request(app, "POST", "/api/tasks", {"id": "t-1", "title": "First block"})
    t2 = await _request(app, "POST", "/api/tasks", {"id": "t-2", "title": "Second block"})
    assert (t1[0], t2[0]) == (201, 201)
    plan = {
        "id": "p-1",
        "date": DEFAULT_MOMENT.date().isoformat(),
        "slots": [{"sector": 1, "task_id": "t-1"}, {"sector": 2, "task_id": "t-2"}],
    }
    upsert = await _request(app, "PUT", f"/api/day-plans/{plan['date']}", plan)
    assert upsert[0] == 200, upsert
    created = await _request(app, "POST", "/api/sessions", {"day_plan_id": "p-1", "settings": FAST})
    assert created[0] == HTTPStatus.CREATED, created
    session_id: str = json.loads(created[1])["id"]
    return session_id


@pytest.mark.api
def test_stream_headers_and_snapshot_when_session_live(sse_app):
    app, _clock = sse_app

    async def scenario() -> dict[str, Any]:
        session_id = await _start_session(app)
        async with _Stream(app, f"/api/sessions/{session_id}/events") as stream:
            assert stream.status == HTTPStatus.OK
            assert stream.headers[b"content-type"].startswith(b"text/event-stream")
            assert stream.headers[b"cache-control"] == b"no-cache"
            assert stream.headers[b"x-accel-buffering"] == b"no"
            name, data = await stream.next_event()
            assert name == "snapshot"
            return data

    snapshot = asyncio.run(scenario())
    assert snapshot["phase"] == "work"
    assert snapshot["remaining_sec"] == 10 * 60
    assert snapshot["server_now"] == DEFAULT_MOMENT.isoformat()


@pytest.mark.api
def test_stream_emits_closed_and_phase_events_when_clock_crosses_deadline(sse_app):
    app, clock = sse_app

    async def scenario() -> list[tuple[str, dict[str, Any]]]:
        session_id = await _start_session(app)
        async with _Stream(app, f"/api/sessions/{session_id}/events") as stream:
            frames = [await stream.next_event()]  # snapshot pins the connect
            clock.advance(timedelta(minutes=10))  # the 10-min WORK ends
            frames.append(await stream.next_event())
            frames.append(await stream.next_event())
            return frames

    frames = asyncio.run(scenario())
    assert [name for name, _ in frames] == ["snapshot", "segment_closed", "phase_changed"]
    assert frames[1][1] == {
        "segment_id": frames[0][1]["timeline"][0]["id"],
        "status": "completed",
    }
    assert frames[2][1]["phase"] == "break"
    assert frames[2][1]["remaining_sec"] == 5 * 60


@pytest.mark.api
def test_stream_finishes_when_session_stops_and_body_closes(sse_app):
    app, _clock = sse_app

    async def scenario() -> list[tuple[str, dict[str, Any]]]:
        session_id = await _start_session(app)
        async with _Stream(app, f"/api/sessions/{session_id}/events") as stream:
            frames = [await stream.next_event()]  # snapshot pins the connect
            stopped = await _request(app, "POST", f"/api/sessions/{session_id}/stop")
            assert stopped[0] == HTTPStatus.OK, stopped
            frames.append(await stream.next_event())
            frames.append(await stream.next_event())
            # the generator returned: the body is closed, nothing follows
            final = await asyncio.wait_for(stream._queue.get(), FRAME_TIMEOUT_SEC)
            assert final["type"] == "http.response.body"
            assert final.get("body", b"") == b"" and not final.get("more_body")
            return frames

    frames = asyncio.run(scenario())
    assert [name for name, _ in frames] == ["snapshot", "segment_closed", "session_finished"]
    assert frames[1][1]["status"] == "interrupted"
    assert frames[2][1]["state"] == "stopped"


@pytest.mark.api
def test_stream_404s_with_json_envelope_when_session_unknown(sse_app):
    app, _clock = sse_app

    async def scenario() -> tuple[int, bytes, dict[bytes, bytes]]:
        return await _request(app, "GET", "/api/sessions/ghost/events")

    status, body, headers = asyncio.run(scenario())
    assert status == HTTPStatus.NOT_FOUND
    assert json.loads(body)["detail"]["code"] == "not_found"
    assert not headers[b"content-type"].startswith(b"text/event-stream")


@pytest.mark.api
def test_ping_comment_frame_arrives_between_silent_events(sse_app):
    app, _clock = sse_app

    async def scenario() -> str:
        app.state.sse_ping_interval_sec = 0.005  # only this test lets pings through
        session_id = await _start_session(app)
        async with _Stream(app, f"/api/sessions/{session_id}/events") as stream:
            # nothing else happens (frozen clock): only a ping can follow
            return await stream.raw_until(PING_FRAME.strip())

    text = asyncio.run(scenario())
    assert "event: snapshot" in text.split(":ping")[0]  # data first, then keepalive


@pytest.mark.unit
def test_ping_defaults_follow_spec_constants():
    # 15 s beats common 30-60 s proxy idle timeouts; the comment frame is
    # ignored by EventSource clients and counted as traffic by proxies.
    # Pinned so a silent edit fails loudly.
    assert PING_INTERVAL_SEC == 15.0
    assert PING_FRAME == ":ping\n\n"
