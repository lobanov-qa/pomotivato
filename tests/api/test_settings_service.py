"""Service floor for settings: defaults, persistence, V5 rejection."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from pomotivato.core.errors import SettingsValidationError
from pomotivato.core.models import SessionSettings
from tests.factories.core_models import settings_factory


@pytest.mark.api
def test_session_settings_default_when_never_written(database, call):
    async def scenario() -> Any:
        async with call() as svc:
            return await svc.settings.get_session_settings()

    settings = asyncio.run(scenario())

    assert settings == SessionSettings()


@pytest.mark.api
def test_session_settings_persist_when_valid_values_written(database, call):
    async def scenario() -> Any:
        custom = settings_factory(work_min=50, break_min=10, long_break_every=3)
        async with call() as svc:
            await svc.settings.put_session_settings(custom)
        async with call() as svc:
            return await svc.settings.get_session_settings()

    stored = asyncio.run(scenario())

    assert stored.work_min == 50
    assert stored.break_min == 10
    assert stored.long_break_every == 3


@pytest.mark.api
def test_session_settings_rejected_when_minutes_out_of_v5_range(database, call):
    async def scenario() -> Any:
        async with call() as svc:
            await svc.settings.put_session_settings(settings_factory(work_min=500))

    with pytest.raises(SettingsValidationError):
        asyncio.run(scenario())


@pytest.mark.api
def test_ui_write_through_keeps_sound_and_signal_neighbors(database, call):
    """set_require_science_fields (V8 toggle) must not reset the A21/DF33
    switches it does not own — the earlier version rewrote the whole blob
    from defaults and silently re-enabled a muted timer."""

    async def scenario() -> Any:
        async with call() as svc:
            await svc.settings.put_ui_settings(6, "auto", False, True, 10, False, "siren")
        async with call() as svc:
            await svc.settings.set_require_science_fields(True)
        async with call() as svc:
            return await svc.settings.get_ui_settings()

    ui = asyncio.run(scenario())

    assert ui.require_science_fields is True  # the toggle itself worked
    assert ui.sound_enabled is False  # untouched neighbors survived
    assert ui.signal_kind == "siren"
