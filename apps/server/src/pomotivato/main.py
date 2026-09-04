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

from pomotivato.infra.db import Database, default_db_path
from pomotivato.infra.migrations import migrate

WEB_DIST = Path(__file__).resolve().parents[3] / "web" / "dist"


def health() -> dict[str, str]:
    """Report liveness for humans, scripts and CI."""
    return {"status": "ok"}


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Bring the schema to head before the first request is served."""
    db: Database = app.state.db
    await migrate(db.db_path)
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
