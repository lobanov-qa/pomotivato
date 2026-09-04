"""Programmatic Alembic runner shared by app lifespan and tests (spec 02 §3).

Desktop users never run a CLI, so the app upgrades its own database on
startup; tests call the same entry points against a temp file and assert
the up/down/up roundtrip (DoD E2). The sync URL lets Alembic own its
connection — WAL readers are unaffected (SQLite file-level journal).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config

import pomotivato
from pomotivato.infra.db import sync_url

SERVER_ROOT = Path(pomotivato.__file__).resolve().parents[2]
INI_PATH = SERVER_ROOT / "alembic.ini"
SCRIPT_LOCATION = SERVER_ROOT / "alembic"

HEAD = "head"
BASE = "base"


def _config(db_path: Path) -> Config:
    config = Config(str(INI_PATH))
    config.set_main_option("script_location", str(SCRIPT_LOCATION))
    # set_main_option interpolates %; paths may legitimately contain it.
    config.set_main_option("sqlalchemy.url", sync_url(db_path).replace("%", "%%"))
    return config


def upgrade_db(db_path: Path, revision: str = HEAD) -> None:
    """Migrate the database at `db_path` forward (or to `base` = downgrade all)."""
    if revision == BASE:
        command.downgrade(_config(db_path), BASE)
    else:
        command.upgrade(_config(db_path), revision)


async def migrate(db_path: Path, revision: str = HEAD) -> None:
    """Async wrapper: Alembic is sync, keep the event loop responsive."""
    await asyncio.to_thread(upgrade_db, db_path, revision)
