"""SettingsService: session settings and planning policy flags (spec 02 §4/§6).

Values are JSON-encoded via core serializers; defaults come from the core
dataclass itself, so there is one list of defaults in the codebase (DRY).
"""

from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession

from pomotivato.core.models import SessionSettings, session_settings_from_dict, to_dict
from pomotivato.core.validation import validate_settings
from pomotivato.infra.repository import SettingRepository

SESSION_SETTINGS_KEY = "***"
REQUIRE_SCIENCE_FIELDS_KEY = "***"


class SettingsService:
    """Read/write app-wide settings with core validation on write."""

    def __init__(self, session: AsyncSession) -> None:
        self._repo = SettingRepository(session)

    async def get_session_settings(self) -> SessionSettings:
        raw = await self._repo.get(SESSION_SETTINGS_KEY)
        if raw is None:
            return SessionSettings()
        return session_settings_from_dict(json.loads(raw))

    async def put_session_settings(self, settings: SessionSettings) -> None:
        validate_settings(settings)
        await self._repo.set(SESSION_SETTINGS_KEY, json.dumps(to_dict(settings)))

    async def require_science_fields(self) -> bool:
        raw = await self._repo.get(REQUIRE_SCIENCE_FIELDS_KEY)
        return False if raw is None else bool(json.loads(raw))

    async def set_require_science_fields(self, value: bool) -> None:
        await self._repo.set(REQUIRE_SCIENCE_FIELDS_KEY, json.dumps(bool(value)))
