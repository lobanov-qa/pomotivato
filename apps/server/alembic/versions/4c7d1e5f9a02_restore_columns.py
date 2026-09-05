"""add restore columns (sessions.slots_json, sessions.pause_started_at,
segments.paused_sec)

Revision ID: 4c7d1e5f9a02
Revises: a908dcc2521c
Create Date: 2026-09-05 15:20:00.000000

Additive-only (spec 02 rule / master §8.4): every new column is nullable or
carries a server default, so legacy rows keep working and the Q4-style
sweep handles anything that cannot be restored.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4c7d1e5f9a02"
down_revision: str | None = "a908dcc2521c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("sessions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("slots_json", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("pause_started_at", sa.Text(), nullable=True))
    with op.batch_alter_table("segments", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("paused_sec", sa.Integer(), nullable=False, server_default="0")
        )


def downgrade() -> None:
    with op.batch_alter_table("segments", schema=None) as batch_op:
        batch_op.drop_column("paused_sec")
    with op.batch_alter_table("sessions", schema=None) as batch_op:
        batch_op.drop_column("pause_started_at")
        batch_op.drop_column("slots_json")
