"""reviews.score -> nullable (E4c, spec 07 §3.1/§3.3 p.4, V24/A18)

Revision ID: b7e02c9a4d13
Revises: 9d41c07be3f8
Create Date: 2026-10-02 16:40:00.000000

NULL is a verdict ("Пропустить"), not missing data. SQLite can drop NOT
NULL only by recreating the table, so this goes through batch_alter_table
(the initial_schema precedent: a908dcc2521c). Existing rows keep their
scores; downgrade restores NOT NULL and is CI-checked up/down/up.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7e02c9a4d13"
down_revision: str | None = "9d41c07be3f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("reviews", schema=None) as batch_op:
        batch_op.alter_column("score", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("reviews", schema=None) as batch_op:
        batch_op.alter_column("score", existing_type=sa.Integer(), nullable=False)
