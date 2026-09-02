"""Application entrypoint.

Stage E0: the API surface is a liveness probe plus a placeholder root
response (or the built frontend when present). Real routers arrive with
the data-layer stage (E2).
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

app = FastAPI(
    title="Pomotivato",
    version="0.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

# One process serves UI + API: if the frontend has been built next to the
# server package (repo layout apps/web/dist, or bundled by PyInstaller),
# mount it at root; otherwise answer with a placeholder.
_WEB_DIST = Path(__file__).resolve().parents[3] / "web" / "dist"


@app.get("/health")
def health() -> dict[str, str]:
    """Report liveness for humans, scripts and CI."""
    return {"status": "ok"}


if _WEB_DIST.is_dir():
    app.mount("/", StaticFiles(directory=_WEB_DIST, html=True), name="web")
else:

    @app.get("/")
    def hello() -> dict[str, str]:
        """Placeholder root response until the frontend build is served."""
        return {"message": "Pomotivato server is running; web UI not built yet"}
