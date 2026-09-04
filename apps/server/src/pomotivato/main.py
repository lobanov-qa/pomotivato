"""Application entrypoint.

E0 gave the liveness probe; E2 (spec 02 §3) turns the module-level app into
a factory over a database path so tests can create_app(tmp_path/x.db) and a
packaged binary defaults to the user data directory. Real routers arrive in
the next PRs of the E2 chain.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from pomotivato.api.errors import register_error_handlers
from pomotivato.api.routers import day_plans, reviews, sessions, settings, tasks
from pomotivato.core.clock import SystemClock
from pomotivato.infra.db import Database, default_db_path
from pomotivato.infra.migrations import migrate
from pomotivato.infra.repository_sessions import finalize_orphan_sessions
from pomotivato.services.session_service import FsmRegistry

WEB_DIST = Path(__file__).resolve().parents[3] / "web" / "dist"


def health() -> dict[str, str]:
    """Report liveness for humans, scripts and CI."""
    return {"status": "ok"}


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Bring the schema to head, then sweep sessions orphaned by a restart."""
    db: Database = app.state.db
    await migrate(db.db_path)
    async with db.new_session() as session:
        await finalize_orphan_sessions(session)
    yield
    await db.dispose()


def create_app(db_path: Path | None = None) -> FastAPI:
    """Assemble the FastAPI app bound to one SQLite database file."""
    app = FastAPI(
        title="Pomotivato",
        version="0.0.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=_lifespan,
    )
    app.state.db = Database(db_path if db_path is not None else default_db_path())
    app.state.clock = SystemClock()
    app.state.fsm_registry = FsmRegistry()
    register_error_handlers(app)
    app.include_router(tasks.router)
    app.include_router(day_plans.router)
    app.include_router(settings.router)
    app.include_router(sessions.router)
    app.include_router(reviews.router)
    app.get("/health")(health)

    # One process serves UI + API: if the frontend has been built next to
    # the server package (repo layout apps/web/dist, or bundled by
    # PyInstaller), mount it at root; otherwise answer with a placeholder.
    if WEB_DIST.is_dir():
        app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
    else:

        @app.get("/")
        def hello() -> dict[str, str]:
            """Placeholder root response until the frontend build is served."""
            return {"message": "Pomotivato server is running; web UI not built yet"}

    return app


app = create_app()
