"""HTTP floor for GET /api/export (spec 04 §4.3): bytes, not DTOs.

The FakeClock fixes "now" so `exported_at` and the default filename are
assertable. Content-Disposition and BOM/encoding are the contract bits.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from http import HTTPStatus
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pomotivato.core.clock import FakeClock
from pomotivato.main import create_app
from tests.factories.core_models import DEFAULT_MOMENT

FAST = {
    "work_min": 10,
    "break_min": 5,
    "long_break_min": 15,
    "long_break_every": 2,
    "auto_start_next": True,
}
DAY = DEFAULT_MOMENT.date().isoformat()


@pytest.fixture
def http_app(tmp_path: Path) -> Iterator[tuple[TestClient, FakeClock]]:
    """Client over temp DB with one day-plan and a completed work segment."""
    app = create_app(tmp_path / "export-test.db")
    clock = FakeClock(DEFAULT_MOMENT)
    app.state.clock = clock
    with TestClient(app) as client:
        client.post("/api/tasks", json={"id": "t-1", "title": "Block A"})
        client.put(
            f"/api/day-plans/{DAY}",
            json={"id": "p-1", "date": DAY, "slots": [{"sector": 1, "task_id": "t-1"}]},
        )
        session_id = client.post(
            "/api/sessions", json={"day_plan_id": "p-1", "settings": FAST}
        ).json()["id"]
        clock.advance(timedelta(minutes=10))
        segment_id = client.get(f"/api/sessions/{session_id}").json()["timeline"][0]["id"]
        client.post("/api/reviews", json={"segment_id": segment_id, "score": 3})
        client.post(f"/api/sessions/{session_id}/stop")
        yield client, clock


@pytest.mark.api
def test_export_json_returns_full_document_with_task_catalog(http_app):
    client, _clock = http_app

    response = client.get("/api/export", params={"format": "json"})
    assert response.status_code == HTTPStatus.OK

    body = response.json()
    # The fixture advanced the clock 10 minutes while running the session;
    # exported_at is whatever "now" the server clock holds.
    server_now = client.get("/api/status").json()["server_now"]
    assert body["exported_at"] == server_now
    assert [t["id"] for t in body["tasks"]] == ["t-1"]
    assert [p["date"] for p in body["day_plans"]] == [DAY]
    assert len(body["sessions"]) == 1
    assert [s["phase"] for s in body["segments"] if s["status"] == "completed"] == ["work"]
    assert body["reviews"][0]["score"] == 3


@pytest.mark.api
def test_export_json_filename_carries_period(http_app):
    client, _clock = http_app

    response = client.get("/api/export", params={"format": "json", "from": "2026-09-01", "to": DAY})

    disposition = response.headers["content-disposition"]
    assert "attachment" in disposition
    assert "pomotivato-export-2026-09-01_" + DAY + ".json" in disposition


@pytest.mark.api
def test_export_csv_returns_utf8_bom_table_with_score_join(http_app):
    client, _clock = http_app

    response = client.get("/api/export", params={"format": "csv"})
    assert response.status_code == HTTPStatus.OK
    assert response.headers["content-type"].startswith("text/csv")
    raw = response.content
    assert raw.startswith(b"\xef\xbb\xbf")  # utf-8-sig BOM per spec ⚑ Q7
    decoded = raw.decode("utf-8-sig")

    header, *rows = decoded.splitlines()
    assert header == (
        "session_id,segment_id,task_id,phase,status,"
        "started_at,ended_at,duration_min,planned_min,score"
    )
    completed = [r for r in rows if r.split(",")[3] == "work" and r.split(",")[4] == "completed"]
    assert len(completed) == 1
    assert completed[0].split(",")[-1] == "3"


@pytest.mark.api
def test_export_default_period_is_last_30_days(http_app):
    client, _clock = http_app

    response = client.get("/api/export", params={"format": "json"})
    default_body = response.json()

    full = client.get(
        "/api/export", params={"format": "json", "from": "2026-01-01", "to": "2026-12-31"}
    ).json()

    assert (
        default_body["period"]["from"] == (DEFAULT_MOMENT - timedelta(days=29)).date().isoformat()
    )
    assert default_body["period"]["to"] == DAY
    # An all-years window sees at least as many rows as the default 30 days.
    assert len(full["day_plans"]) >= len(default_body["day_plans"])


@pytest.mark.api
def test_export_rejects_unknown_format_and_bad_period(http_app):
    client, _clock = http_app

    unknown = client.get("/api/export", params={"format": "xml"})
    reversed_ = client.get(
        "/api/export", params={"format": "json", "from": "2026-09-07", "to": "2026-09-01"}
    )
    too_long = client.get(
        "/api/export", params={"format": "json", "from": "2020-01-01", "to": "2026-01-01"}
    )

    assert unknown.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert reversed_.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert too_long.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
