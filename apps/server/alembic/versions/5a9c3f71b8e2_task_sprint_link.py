"""add tasks.sprint_id (E4c, spec 07 §3.1, ADR-0005)

Revision ID: 5a9c3f71b8e2
Revises: 3c9f80e2d1a7
Create Date: 2026-09-26 11:30:00.000000

Additive-only (master §8.4): the sprint container gets a real owner column —
nullable TEXT with an FK to sprints and an index (spec 07 §3.3 p.1). NULL
means the dateless "no sprint" sandbox (A8/A24), so every pre-existing row
stays loadable and unscheduled. carry_choice arrives with the lifecycle PR
(spec 07 §8 line 2), not here. Downgrade drops the column.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5a9c3f71b8e2"
down_revision: str | None = "3c9f80e2d1a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.add_column(sa.Column("sprint_id", sa.Text(), nullable=True))
        batch_op.create_index(batch_op.f("ix_tasks_sprint_id"), ["sprint_id"], unique=False)
        batch_op.create_foreign_key(
            batch_op.f("fk_tasks_sprint_id_sprints"), "sprints", ["sprint_id"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_tasks_sprint_id"))
        batch_op.drop_constraint(batch_op.f("fk_tasks_sprint_id_sprints"), type_="foreignkey")
        batch_op.drop_column("sprint_id")
