"""HTTP floor for the day-close wave (E4c PR 4, spec 07 §5.6-§5.7, §4.7).

V21 past marks refused (existing history lives); A28 entering work marks
today; V27 «В работе» only in a sprint covering today; V30 a forgotten DOING
card folds on the first read of a new day; V33 a live session shields its
cards from the fold until it stops; V31 a missed tick blocks the drag into
«Готово»; V32 the close endpoint re-checks and closes without a timer rerun.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from http import HTTPStatus
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from pomotivato.core.clock import FakeClock
from pomotivato.main import create_app
from tests.api.schemas_http import put_in_work
from tests.factories.core_models import DEFAULT_MOMENT

FAST = {
    "work_min": 10,
    "break_min": 5,
    "long_break_min": 15,
    "long_break_every": 4,
    "auto_start_next": False,
}
TODAY = DEFAULT_MOMENT.date()


@pytest.fixture
def day_app(tmp_path: Path) -> Iterator[tuple[TestClient, FakeClock]]:
    app = create_app(tmp_path / "day-close-test.db")
    clock = FakeClock(DEFAULT_MOMENT)
    app.state.clock = clock
    with TestClient(app) as client:
        yield client, clock


def make_sprint(client: TestClient, start: str, end: str, *, active: bool = True) -> str:
    response = client.post("/api/sprints", json={"start_date": start, "end_date": end})
    assert response.status_code == HTTPStatus.CREATED, response.text
    sprint_id = str(response.json()["id"])
    if active:
        up = client.patch(f"/api/sprints/{sprint_id}", json={"status": "active"})
        assert up.status_code == HTTPStatus.OK, up.text
    return sprint_id


def make_task(client: TestClient, task_id: str, **body: object) -> dict[str, Any]:
    payload: dict[str, object] = {"id": task_id, "title": f"Card {task_id}", **body}
    response = client.post("/api/tasks", json=payload)
    assert response.status_code == HTTPStatus.CREATED, response.text
    return dict(response.json())


def plan_day(client: TestClient, day: str, task_ids: list[str]) -> None:
    plan = {
        "id": f"p-{day}",
        "date": day,
        "slots": [{"sector": n + 1, "task_id": tid} for n, tid in enumerate(task_ids)],
    }
    response = client.put(f"/api/day-plans/{day}", json=plan)
    assert response.status_code == HTTPStatus.OK, response.text


@pytest.mark.api
def test_creating_a_card_with_a_past_mark_is_refused_when_v21_breaks(
    day_app: tuple[TestClient, FakeClock],
) -> None:
    """Author's bug (2) 24.09, server half: labels are not time machines."""
    client, _ = day_app

    bad = client.post(
        "/api/tasks",
        json={
            "id": "t-past",
            "title": "Backdated",
            "recurrence": {"kind": "on_dates", "days": ["2026-09-01"]},
        },
    )

    assert bad.status_code == HTTPStatus.UNPROCESSABLE_ENTITY  # V21: invalid request
    assert "past" in bad.json()["detail"]["message"]


@pytest.mark.api
def test_adding_a_past_mark_to_an_existing_card_is_refused_history_stays(
    day_app: tuple[TestClient, FakeClock],
) -> None:
    client, _ = day_app
    card = make_task(client, "t-hist", recurrence={"kind": "on_dates", "days": [TODAY.isoformat()]})

    sneaky = client.patch(
        f"/api/tasks/{card['id']}",
        json={"recurrence": {"kind": "on_dates", "days": [TODAY.isoformat(), "2026-09-01"]}},
    )

    assert sneaky.status_code == HTTPStatus.UNPROCESSABLE_ENTITY  # V21 request rule
    fresh = client.get(f"/api/tasks/{card['id']}").json()
    assert fresh["recurrence"]["days"] == [TODAY.isoformat()]  # nothing stuck


@pytest.mark.api
def test_entering_work_marks_today_when_the_card_had_no_tick(
    day_app: tuple[TestClient, FakeClock],
) -> None:
    """A28/S2: drag to «В работе» on an unmarked day extends the plan there."""
    client, _ = day_app
    sprint = make_sprint(client, TODAY.isoformat(), "2026-09-07")
    card = make_task(client, "t-untouched", sprint_id=sprint)

    doing = client.post(f"/api/tasks/{card['id']}/status", json={"to": "planned"})
    assert doing.status_code == HTTPStatus.OK
    into = client.post(f"/api/tasks/{card['id']}/status", json={"to": "doing"})

    assert into.status_code == HTTPStatus.OK
    body = into.json()
    assert body["recurrence"]["kind"] == "on_dates"
    assert body["recurrence"]["days"] == [TODAY.isoformat()]  # auto-marked
    # hint inputs come with the board scan (spec 07 §4.7)
    listed = {item["id"]: item for item in client.get("/api/tasks").json()}
    assert listed[card["id"]]["days_left"] == []
    assert listed[card["id"]]["closeable"] is False  # no finished block yet


@pytest.mark.api
def test_doing_in_a_sprint_that_does_not_cover_today_is_refused(
    day_app: tuple[TestClient, FakeClock],
) -> None:
    """V27/A23: a future sprint holds backlog/planned only; «В работе» says
    "today" and the server keeps that meaning."""
    client, _ = day_app
    future = make_sprint(client, "2026-09-05", "2026-09-09")
    card = make_task(client, "t-future", sprint_id=future)

    planned = client.post(f"/api/tasks/{card['id']}/status", json={"to": "planned"})
    assert planned.status_code == HTTPStatus.OK
    refused = client.post(f"/api/tasks/{card['id']}/status", json={"to": "doing"})

    assert refused.status_code == HTTPStatus.CONFLICT
    assert "covers today" in refused.json()["detail"]["message"]


@pytest.mark.api
def test_a_forgotten_doing_card_folds_on_the_first_read_of_a_new_day(
    day_app: tuple[TestClient, FakeClock],
) -> None:
    """V30/S6: DOING without sectors tomorrow morning -> back to planned."""
    client, clock = day_app
    sprint = make_sprint(client, TODAY.isoformat(), "2026-09-10")
    make_task(
        client,
        "t-left",
        sprint_id=sprint,
        recurrence={"kind": "on_dates", "days": ["2026-09-10"]},
    )
    put_in_work(client, "t-left")

    clock.advance(timedelta(days=1))  # 09-04: no plan slots for the card
    folded = {item["id"]: item for item in client.get("/api/tasks").json()}

    assert folded["t-left"]["status"] == "planned"
    again = client.get("/api/tasks").json()  # fold is idempotent
    assert [t["status"] for t in again if t["id"] == "t-left"] == ["planned"]


@pytest.mark.api
def test_a_live_session_shields_its_cards_from_the_fold_until_it_stops(
    day_app: tuple[TestClient, FakeClock],
) -> None:
    """V33/A37: night past midnight with the dial still open — fold waits."""
    client, clock = day_app
    sprint = make_sprint(client, TODAY.isoformat(), "2026-09-10")
    make_task(
        client,
        "t-night",
        sprint_id=sprint,
        recurrence={"kind": "on_dates", "days": ["2026-09-10"]},
    )
    put_in_work(client, "t-night")
    plan_day(client, TODAY.isoformat(), ["t-night"])
    session = client.post("/api/sessions", json={"day_plan_id": f"p-{TODAY}", "settings": FAST})
    assert session.status_code == HTTPStatus.CREATED

    clock.advance(timedelta(days=1))  # past midnight, session never stopped
    items = {item["id"]: item for item in client.get("/api/tasks").json()}
    assert items["t-night"]["status"] == "doing"  # V33: the fold keeps its hands off

    client.post(f"/api/sessions/{session.json()['id']}/stop")
    after = {item["id"]: item for item in client.get("/api/tasks").json()}
    assert after["t-night"]["status"] == "planned"  # only now the fold may pass


@pytest.mark.api
def test_dragging_a_card_with_a_missed_day_into_done_is_refused(
    day_app: tuple[TestClient, FakeClock],
) -> None:
    """V31/S1: the hole in the calendar blocks «Готово» by drag — the server
    checks it straight from the stored card, before any lazy fold can."""
    client, clock = day_app
    sprint = make_sprint(client, TODAY.isoformat(), "2026-09-07")
    make_task(
        client,
        "t-hole",
        sprint_id=sprint,
        recurrence={"kind": "on_dates", "days": [TODAY.isoformat(), "2026-09-04"]},
    )
    put_in_work(client, "t-hole")
    clock.advance(timedelta(days=2))  # 09-05: both ticks are past, none worked

    refused = client.post("/api/tasks/t-hole/status", json={"to": "done"})

    assert refused.status_code == HTTPStatus.CONFLICT
    assert "missed day" in refused.json()["detail"]["message"]
    # the board scan (which also folds now) explains the hole to the panel
    listed = {item["id"]: item for item in client.get("/api/tasks").json()}
    assert listed["t-hole"]["days_missed"] == [TODAY.isoformat(), "2026-09-04"]


@pytest.mark.api
def test_close_endpoint_finishes_a_card_whose_dates_ran_out(
    day_app: tuple[TestClient, FakeClock],
) -> None:
    """V32/A35 (S14): dialog -> POST /close; no timer rerun, honest re-check."""
    client, clock = day_app
    sprint = make_sprint(client, TODAY.isoformat(), "2026-09-04")
    card = make_task(
        client,
        "t-close",
        sprint_id=sprint,
        recurrence={"kind": "on_dates", "days": [TODAY.isoformat()]},
    )
    put_in_work(client, card["id"])
    plan_day(client, TODAY.isoformat(), [card["id"]])
    session = client.post(
        "/api/sessions", json={"day_plan_id": f"p-{TODAY}", "settings": FAST}
    ).json()
    clock.advance(timedelta(minutes=10))  # the block completes into the break
    client.get(f"/api/sessions/{session['id']}")  # catch-up persists the segment

    closed = client.post(f"/api/tasks/{card['id']}/close")

    assert closed.status_code == HTTPStatus.OK, closed.text
    assert closed.json()["status"] == "done"
    listed = {item["id"]: item for item in client.get("/api/tasks").json()}
    assert listed[card["id"]]["days_left"] == []
    assert listed[card["id"]]["closeable"] is False  # already done: nothing to close


@pytest.mark.api
def test_close_refuses_a_card_that_never_worked_or_has_days_ahead(
    day_app: tuple[TestClient, FakeClock],
) -> None:
    client, _ = day_app
    sprint = make_sprint(client, TODAY.isoformat(), "2026-09-07")
    fresh = make_task(
        client,
        "t-new",
        sprint_id=sprint,
        recurrence={"kind": "on_dates", "days": ["2026-09-06"]},
    )

    refused = client.post(f"/api/tasks/{fresh['id']}/close")

    assert refused.status_code == HTTPStatus.CONFLICT
    assert "not closeable" in refused.json()["detail"]["message"]
    assert refused.json() is not None  # envelope intact
    assert client.get(f"/api/tasks/{fresh['id']}").json()["status"] == "backlog"
