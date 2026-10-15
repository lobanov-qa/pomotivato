"""HTTP floor for the focus workspace wave (E4c PR 8, spec 07 §4.4/§5.2/§5.6).

V17 red. 5.6: the start happens IN a scope — a sprint scope must cover
today and only its own doing cards count; the shelf counts sprint-less
ones; omitting the scope keeps the pre-E4c law. V25/A4: «Обновить статус»
carries today's ticked cards of the scope into work or refuses the whole
move with the over-count in the text; no_timer errands, UNTICKED and
SHELF cards stay out of the selection (§5.2 formula, sprint scope only).
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
from tests.factories.core_models import DEFAULT_MOMENT

TODAY = DEFAULT_MOMENT.date().isoformat()  # 2026-09-03


@pytest.fixture
def focus_app(tmp_path: Path) -> Iterator[tuple[TestClient, FakeClock]]:
    app = create_app(tmp_path / "focus-test.db")
    clock = FakeClock(DEFAULT_MOMENT)
    app.state.clock = clock
    with TestClient(app) as client:
        yield client, clock


def make_sprint(client: TestClient, start: str, end: str) -> str:
    response = client.post("/api/sprints", json={"start_date": start, "end_date": end})
    assert response.status_code == HTTPStatus.CREATED, response.text
    sprint_id = str(response.json()["id"])
    up = client.patch(f"/api/sprints/{sprint_id}", json={"status": "active"})
    assert up.status_code == HTTPStatus.OK, up.text
    return sprint_id


def make_task(client: TestClient, task_id: str, **body: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"id": task_id, "title": f"Card {task_id}", **body}
    response = client.post("/api/tasks", json=payload)
    assert response.status_code == HTTPStatus.CREATED, response.text
    return dict(response.json())


def ticked(*days: str) -> dict[str, Any]:
    return {"recurrence": {"kind": "on_dates", "days": list(days or [TODAY])}}


def status_of(client: TestClient, task_id: str) -> str:
    response = client.get(f"/api/tasks/{task_id}")
    assert response.status_code == HTTPStatus.OK
    return str(response.json()["status"])


def put_plan(client: TestClient, task_ids: list[str]) -> str:
    plan = {
        "id": f"plan-{TODAY}",
        "date": TODAY,
        "slots": [{"sector": n + 1, "task_id": tid} for n, tid in enumerate(task_ids)],
    }
    response = client.put(f"/api/day-plans/{TODAY}", json=plan)
    assert response.status_code == HTTPStatus.OK, response.text
    return str(response.json()["id"])


def move_to(client: TestClient, task_id: str, *statuses: str) -> None:
    for status in statuses:
        response = client.post(f"/api/tasks/{task_id}/status", json={"to": status})
        assert response.status_code == HTTPStatus.OK, response.text


@pytest.mark.api
def test_refresh_moves_ticked_scope_cards_into_work(
    focus_app: tuple[TestClient, FakeClock],
) -> None:
    """§5.2: scope ∩ (backlog|planned) ∩ ticked today ∩ timer -> DOING."""
    client, _clock = focus_app
    sprint = make_sprint(client, TODAY, "2026-09-07")
    make_task(client, "t-back", sprint_id=sprint, **ticked())
    make_task(client, "t-plan", sprint_id=sprint, **ticked())
    make_task(client, "t-unticked", sprint_id=sprint)
    make_task(client, "t-errand", sprint_id=sprint, no_timer=True, **ticked())
    move_to(client, "t-plan", "planned")

    response = client.post(f"/api/day-plans/{TODAY}/refresh-status", json={"sprint_id": sprint})

    assert response.status_code == HTTPStatus.OK, response.text
    assert response.json() == {"moved": 2}
    assert status_of(client, "t-back") == "doing"
    assert status_of(client, "t-plan") == "doing"
    assert status_of(client, "t-unticked") == "backlog"  # no tick today: stays out (§5.2)
    assert status_of(client, "t-errand") == "backlog"  # no_timer never joins the dial (A5)


@pytest.mark.api
def test_refresh_shelf_scope_moves_only_shelf_cards(
    focus_app: tuple[TestClient, FakeClock],
) -> None:
    """§5.2 with no_sprint=true: the shelf is its own scope; a TICK is still
    required (the §4.4 button is about today's ticked work)."""
    client, _clock = focus_app
    sprint = make_sprint(client, TODAY, "2026-09-07")
    make_task(client, "shelf", **ticked())
    make_task(client, "sprint-owned", sprint_id=sprint, **ticked())

    response = client.post(f"/api/day-plans/{TODAY}/refresh-status", json={"no_sprint": True})

    assert response.json() == {"moved": 1}
    assert status_of(client, "shelf") == "doing"
    assert status_of(client, "sprint-owned") == "backlog"


@pytest.mark.api
def test_refresh_refuses_the_whole_move_when_the_limit_breaks(
    focus_app: tuple[TestClient, FakeClock],
) -> None:
    """V25/A4: overflow refuses everything, the text carries the numbers."""
    client, _clock = focus_app
    sprint = make_sprint(client, TODAY, "2026-09-07")
    client.put("/api/settings/ui", json={"max_in_work": 1, "theme": "auto"})
    make_task(client, "t-a", sprint_id=sprint, **ticked())
    make_task(client, "t-b", sprint_id=sprint, **ticked())
    move_to(client, "t-a", "planned", "doing")  # dial already full (1 of 1)

    bad = client.post(f"/api/day-plans/{TODAY}/refresh-status", json={"sprint_id": sprint})

    assert bad.status_code == HTTPStatus.CONFLICT
    message = bad.json()["detail"]["message"]
    assert "1 of 1 in work" in message and "1 more to move" in message
    assert status_of(client, "t-b") == "backlog"  # refused as a whole (A4)


@pytest.mark.api
def test_refresh_skips_a_card_whose_today_is_already_worked(
    focus_app: tuple[TestClient, FakeClock],
) -> None:
    """DF25 (author 15.10): a multi-day card V22 walked back to «Запланировано»
    after working its day must not be pulled into work again the SAME day —
    the bulk walk is not a second run of a spent day (manual A17 stays)."""
    client, clock = focus_app
    sprint = make_sprint(client, TODAY, "2026-09-07")
    tomorrow = (clock.now().date() + timedelta(days=1)).isoformat()
    make_task(client, "t-two-days", sprint_id=sprint, **ticked(TODAY, tomorrow))
    move_to(client, "t-two-days", "planned", "doing")
    plan_id = put_plan(client, ["t-two-days"])
    started = client.post(
        "/api/sessions",
        json={"day_plan_id": plan_id, "sprint_id": sprint},
    )
    assert started.status_code == HTTPStatus.CREATED, started.text
    session = started.json()
    clock.advance(timedelta(minutes=26))  # work_min 25: the block closes on read
    view = client.get(f"/api/sessions/{session['id']}").json()
    block = next(
        seg for seg in view["timeline"] if seg["phase"] == "work" and seg["status"] == "completed"
    )

    verdict = client.post("/api/reviews", json={"segment_id": block["id"], "score": 3})
    assert verdict.status_code == HTTPStatus.CREATED, verdict.text
    assert status_of(client, "t-two-days") == "planned"  # V22: a future tick remains

    response = client.post(f"/api/day-plans/{TODAY}/refresh-status", json={"sprint_id": sprint})

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"moved": 0}  # the spent day is not re-run (DF25)
    assert status_of(client, "t-two-days") == "planned"


@pytest.mark.api
def test_refresh_materializes_the_plan_so_the_fold_leaves_the_card_in_work(
    focus_app: tuple[TestClient, FakeClock],
) -> None:
    """DF26 (author 15.10): «moved: 1» must not evaporate on the next board
    read — V30 folds every DOING card with no sector in today's plan, so
    the refresh appends the movers' chunks to the plan itself, and the
    card's next ticked day carries it back in and keeps it there."""
    client, clock = focus_app
    sprint = make_sprint(client, TODAY, "2026-09-07")
    day2 = (clock.now().date() + timedelta(days=1)).isoformat()
    make_task(client, "t-two", sprint_id=sprint, **ticked(TODAY, day2))

    first = client.post(f"/api/day-plans/{TODAY}/refresh-status", json={"sprint_id": sprint})

    assert first.json() == {"moved": 1}
    plan = client.get(f"/api/day-plans/{TODAY}").json()
    assert [s["task_id"] for s in plan["slots"]] == ["t-two"]
    listed = {t["id"]: t for t in client.get("/api/tasks").json()}
    assert listed["t-two"]["status"] == "doing"  # the fold has a sector to honour

    # A day passes with no further work: the V30 fold returns the card...
    clock.advance(timedelta(days=1))
    folded = {t["id"]: t for t in client.get("/api/tasks").json()}
    assert folded["t-two"]["status"] == "planned"

    # ...and the next ticked day moves it in for real (the author's flow).
    second = client.post(f"/api/day-plans/{day2}/refresh-status", json={"sprint_id": sprint})

    assert second.json() == {"moved": 1}  # worked_yesterday does not block today
    after = {t["id"]: t for t in client.get("/api/tasks").json()}
    assert after["t-two"]["status"] == "doing"  # and it stays there


@pytest.mark.api
def test_refresh_requires_a_scope_and_a_fresh_date(
    focus_app: tuple[TestClient, FakeClock],
) -> None:
    """§6 grammar: no scope answer is 422; past days are not a surface."""
    client, _clock = focus_app
    empty = client.post(f"/api/day-plans/{TODAY}/refresh-status", json={})
    assert empty.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    past = client.post("/api/day-plans/2020-01-01/refresh-status", json={"no_sprint": True})
    assert past.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.api
def test_start_in_a_sprint_that_does_not_cover_today_is_refused(
    focus_app: tuple[TestClient, FakeClock],
) -> None:
    """V17 red. 5.6: the sprint-scope start names the fix (A23's twin)."""
    client, _clock = focus_app
    future = make_sprint(client, "2026-09-10", "2026-09-14")
    # V19 keeps a sprint card from ticking outside its window, so this is a
    # plain Once card: the sprint guard fires BEFORE any plan/slot scan.
    make_task(client, "t-fut", sprint_id=future)
    plan_id = put_plan(client, ["t-fut"])

    bad = client.post("/api/sessions", json={"day_plan_id": plan_id, "sprint_id": future})

    assert bad.status_code == HTTPStatus.CONFLICT
    assert "does not cover today" in bad.json()["detail"]["message"]


@pytest.mark.api
def test_scoped_start_only_counts_the_scopes_own_doing_cards(
    focus_app: tuple[TestClient, FakeClock],
) -> None:
    """V17: shelf start ignores sprint cards in the plan; the owner's start
    accepts them; an unknown sprint id is a 404."""
    client, _clock = focus_app
    sprint = make_sprint(client, TODAY, "2026-09-07")
    make_task(client, "t-owned", sprint_id=sprint, **ticked())
    move_to(client, "t-owned", "planned", "doing")
    plan_id = put_plan(client, ["t-owned"])

    shelf_start = client.post("/api/sessions", json={"day_plan_id": plan_id, "no_sprint": True})
    assert shelf_start.status_code == HTTPStatus.CONFLICT  # only a sprint card backs the plan
    assert "no task in progress" in shelf_start.json()["detail"]["message"]

    other = client.post("/api/sessions", json={"day_plan_id": plan_id, "sprint_id": "ghost"})
    assert other.status_code == HTTPStatus.NOT_FOUND

    scoped = client.post("/api/sessions", json={"day_plan_id": plan_id, "sprint_id": sprint})
    assert scoped.status_code == HTTPStatus.CREATED


@pytest.mark.api
def test_unscoped_start_keeps_the_pre_e4c_law(focus_app: tuple[TestClient, FakeClock]) -> None:
    """Backward floor: without scope fields any doing card may back a plan."""
    client, _clock = focus_app
    make_task(client, "t-shelf", **ticked())
    move_to(client, "t-shelf", "planned", "doing")
    plan_id = put_plan(client, ["t-shelf"])

    response = client.post("/api/sessions", json={"day_plan_id": plan_id})

    assert response.status_code == HTTPStatus.CREATED
