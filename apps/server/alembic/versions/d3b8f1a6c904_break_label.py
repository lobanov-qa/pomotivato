"""add segments.break_label (E4b special breaks, spec 01 v0.4)

Revision ID: d3b8f1a6c904
Revises: 4c7d1e5f9a02
Create Date: 2026-09-07 18:30:00.000000

Additive-only (master §8.4): one nullable column; every pre-E4b row keeps
working (NULL = not a special break), the downgrade drops it again.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d3b8f1a6c904"
down_revision: str | None = "4c7d1e5f9a02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("segments", schema=None) as batch_op:
        batch_op.add_column(sa.Column("break_label", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("segments", schema=None) as batch_op:
        batch_op.drop_column("break_label")
