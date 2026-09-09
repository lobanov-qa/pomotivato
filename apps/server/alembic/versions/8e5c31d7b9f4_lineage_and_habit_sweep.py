"""add tasks.cloned_from + sweep retired habit type (E4b-UX DF12/DF7)

Revision ID: 8e5c31d7b9f4
Revises: 7f2a9c41de55
Create Date: 2026-09-08 18:20:00.000000

Two steps, one hop (spec 06 §6): a nullable lineage tag for duplicates
(plain Text — no FK, clones must never block the original's delete) and
the habit sweep: TaskType.HABIT is retired in code, so legacy rows move
to 'normal' here or the enum parser would reject them on load.
Downgrade drops the column; the sweep is one-way (the distinction was
never stored anywhere else — honest to note, matches additive doctrine).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8e5c31d7b9f4"
down_revision: str | None = "7f2a9c41de55"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.add_column(sa.Column("cloned_from", sa.Text(), nullable=True))
    op.execute("UPDATE tasks SET type = 'normal' WHERE type = 'habit'")


def downgrade() -> None:
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.drop_column("cloned_from")
