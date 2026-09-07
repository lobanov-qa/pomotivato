"""Export router: GET /api/export?format=json|csv (spec 04 §4.3).

Returns raw bytes with a download filename (Content-Disposition), not a
DTO: the point is a file the user keeps, not a screen. CSV ships as
utf-8-sig so Excel opens Cyrillic titles without a codepage dance.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response

from pomotivato.api.deps import ClockDep, DbSession
from pomotivato.services.export import CSV_MEDIA, ExportService, csv_bytes, json_bytes

router = APIRouter(prefix="/api", tags=["export"])

FORMAT_EXT = {"json": "json", "csv": "csv"}


@router.get("/export")
async def export_data(
    session: DbSession,
    clock: ClockDep,
    format: Annotated[Literal["json", "csv"], Query()] = "json",
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
) -> Response:
    """Stream the whole DB (or a period) as a downloadable file."""
    today = clock.now().date()
    start = date_from if date_from is not None else today - timedelta(days=29)
    end = date_to if date_to is not None else today
    now = clock.now()
    segments, scores, document = await ExportService(session).gather(start, end, now)
    if format == "csv":
        body = csv_bytes(segments, scores)
        media = CSV_MEDIA
    else:
        body = json_bytes(document)
        media = "application/json"
    filename = f"pomotivato-export-{start.isoformat()}_{end.isoformat()}.{FORMAT_EXT[format]}"
    return Response(
        content=body,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
