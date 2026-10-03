"""tasks.done_at: the trim order for «Готово» (E4c, spec 07 §4.6, V26)

Revision ID: c2f5a8d3b916
Revises: b7e02c9a4d13
Create Date: 2026-10-03 11:20:00.000000

V26 trims the done column by the moment a card last entered DONE. The
field did not exist before this feature: rows keep NULL and the trim
falls back to created_at for them (spec 07 §4.6, author's decision on
03.10). Purely additive: no backfill, no constraints, downgrade just
drops the column.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c2f5a8d3b916"
down_revision: str | None = "b7e02c9a4d13"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("tasks") as batch:
        batch.add_column(sa.Column("done_at", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("tasks") as batch:
        batch.drop_column("done_at")
