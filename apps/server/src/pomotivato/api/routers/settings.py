"""Settings router: session settings GET/PUT (spec 02 §5)."""

from __future__ import annotations

from fastapi import APIRouter

from pomotivato.api.deps import DbSession
from pomotivato.api.schemas import SessionSettingsDto
from pomotivato.services.settings_service import SettingsService

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=SessionSettingsDto)
async def get_settings(session: DbSession) -> SessionSettingsDto:
    service = SettingsService(session)
    return SessionSettingsDto.from_core(await service.get_session_settings())


@router.put("", response_model=SessionSettingsDto)
async def put_settings(dto: SessionSettingsDto, session: DbSession) -> SessionSettingsDto:
    service = SettingsService(session)
    settings = dto.to_core()
    await service.put_session_settings(settings)
    return SessionSettingsDto.from_core(settings)
