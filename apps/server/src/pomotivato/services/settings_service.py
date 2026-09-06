"""SettingsService: session settings and planning policy flags (spec 02 §4/§6).

Values are JSON-encoded via core serializers; defaults come from the core
dataclass itself, so there is one list of defaults in the codebase (DRY).
"""

from __future__ import annotations

import json
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from pomotivato.core.errors import ValidationError
from pomotivato.core.models import SessionSettings, session_settings_from_dict, to_dict
from pomotivato.core.validation import validate_settings
from pomotivato.infra.repository import SettingRepository

SESSION_SETTINGS_KEY = "session"
UI_SETTINGS_KEY = "ui"
REQUIRE_SCIENCE_FIELDS_KEY = "require_science_fields"

# Presentation-level enum: themes are a UI concern, so core does not own it.
Theme = Literal["auto", "light", "dark"]

DEFAULT_MAX_IN_WORK = 6  # funnel law: doing == today == the dial (core MAX_SECTOR=12 ceiling)
DEFAULT_THEME: Theme = "auto"  # spec 03 ⚑ Q9: OS-following until the toggle says otherwise


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

    async def get_ui_settings(self) -> tuple[int, Theme]:
        """(max_in_work, theme) with defaults when the key was never set."""
        raw = await self._repo.get(UI_SETTINGS_KEY)
        if raw is None:
            return DEFAULT_MAX_IN_WORK, DEFAULT_THEME
        data = json.loads(raw)
        max_in_work = int(data.get("max_in_work", DEFAULT_MAX_IN_WORK))
        theme = data.get("theme", DEFAULT_THEME)
        return max_in_work, theme if theme in ("auto", "light", "dark") else DEFAULT_THEME

    async def put_ui_settings(self, max_in_work: int, theme: Theme) -> None:
        if not 1 <= max_in_work <= 12:
            msg = f"max_in_work must be 1..12, got {max_in_work}"
            raise ValidationError(msg)
        if theme not in ("auto", "light", "dark"):
            msg = f"unknown theme {theme!r}"
            raise ValidationError(msg)
        await self._repo.set(
            UI_SETTINGS_KEY, json.dumps({"max_in_work": max_in_work, "theme": theme})
        )

    async def require_science_fields(self) -> bool:
        raw = await self._repo.get(REQUIRE_SCIENCE_FIELDS_KEY)
        return False if raw is None else bool(json.loads(raw))

    async def set_require_science_fields(self, value: bool) -> None:
        await self._repo.set(REQUIRE_SCIENCE_FIELDS_KEY, json.dumps(bool(value)))
