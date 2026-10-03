"""add tasks.carry_choice (E4c, spec 07 §3.1 p.2)

Revision ID: 9d41c07be3f8
Revises: 5a9c3f71b8e2
Create Date: 2026-10-02 14:05:00.000000

Additive-only (master §8.4): nullable TEXT with a CHECK ('left', 'moved',
NULL) — the per-card fate at sprint closure (A40/V34). Existing rows get
NULL (no decision). Downgrade drops the column.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9d41c07be3f8"
down_revision: str | None = "5a9c3f71b8e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.add_column(sa.Column("carry_choice", sa.Text(), nullable=True))
        batch_op.create_check_constraint(
            batch_op.f("ck_tasks_carry_choice"),
            "carry_choice IN ('left', 'moved')",
        )


def downgrade() -> None:
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("ck_tasks_carry_choice"), type_="check")
        batch_op.drop_column("carry_choice")
