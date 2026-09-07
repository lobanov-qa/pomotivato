"""create sprints table (E4b F10, ADR-0003 p.3, spec 05 §3.10)

Revision ID: 7f2a9c41de55
Revises: d3b8f1a6c904
Create Date: 2026-09-07 21:40:00.000000

New table only — existing rows untouched; downgrade drops it. Overlap and
single-active rules are enforced in the service layer (SQLite CHECKs would
duplicate calendar math without gaining honesty).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7f2a9c41de55"
down_revision: str | None = "d3b8f1a6c904"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sprints",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("start_date", sa.Text(), nullable=False),
        sa.Column("end_date", sa.Text(), nullable=False),
        sa.Column("goal", sa.Text(), nullable=True),
        sa.Column("done_criteria", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("number"),
    )


def downgrade() -> None:
    op.drop_table("sprints")
