"""add tasks.no_timer (E4b-UX DF13)

Revision ID: 3c9f80e2d1a7
Revises: 8e5c31d7b9f4
Create Date: 2026-09-08 21:05:00.000000

Additive-only (master §8.4): one boolean column with a server default of
0, so every pre-existing row loads as a normal timer task. Downgrade
drops it. The flag is read by the capacity gate, the day planner and the
week preview (services layer); the core enum/status machine untouched.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3c9f80e2d1a7"
down_revision: str | None = "8e5c31d7b9f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("no_timer", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.drop_column("no_timer")
