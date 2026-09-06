"""Settings router: session + ui keys (spec 02 §5, spec 03 §5 ⚑ Q3/Q6).

GET returns the whole dictionary; PUT is per-key (/session, /ui) — the
explicit contract beats a key field in the body (author's Q6 choice).
The old flat PUT /api/settings moved to /api/settings/session in this PR:
an E2 contract change, tests updated in the same diff.
"""

from __future__ import annotations

from fastapi import APIRouter

from pomotivato.api.deps import DbSession
from pomotivato.api.schemas import SessionSettingsDto, SettingsBundleDto, UiSettingsDto
from pomotivato.services.settings_service import SettingsService

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=SettingsBundleDto)
async def get_settings(session: DbSession) -> SettingsBundleDto:
    service = SettingsService(session)
    sectors, theme = await service.get_ui_settings()
    return SettingsBundleDto(
        session=SessionSettingsDto.from_core(await service.get_session_settings()),
        ui=UiSettingsDto(max_in_work=sectors, theme=theme),
    )


@router.put("/session", response_model=SessionSettingsDto)
async def put_session_settings(dto: SessionSettingsDto, session: DbSession) -> SessionSettingsDto:
    service = SettingsService(session)
    settings = dto.to_core()
    await service.put_session_settings(settings)
    return SessionSettingsDto.from_core(settings)


@router.put("/ui", response_model=UiSettingsDto)
async def put_ui_settings(dto: UiSettingsDto, session: DbSession) -> UiSettingsDto:
    service = SettingsService(session)
    await service.put_ui_settings(dto.max_in_work, dto.theme)
    return dto
