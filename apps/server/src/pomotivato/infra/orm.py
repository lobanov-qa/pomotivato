"""SQLAlchemy 2.0 ORM tables (spec 02 §2).

The ORM mirrors master §9; domain semantics live in pomotivato.core, and
JSON-encoded columns are (de)serialized exclusively with core helpers from
the repository layer — the ORM stores plain TEXT, so the format has one
owner. Alembic autogenerate uses Base.metadata as the single source.
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base shared by all pomotivato tables and Alembic."""


class TaskRow(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(Text)
    important: Mapped[bool] = mapped_column(Boolean, default=True)
    urgent: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(Text, index=True)
    estimate_blocks: Mapped[int] = mapped_column(Integer)
    deadline: Mapped[str | None] = mapped_column(Text)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"))
    recurrence_json: Mapped[str] = mapped_column(Text)
    when_then: Mapped[str | None] = mapped_column(Text)
    done_criteria: Mapped[str | None] = mapped_column(Text)
    benefit: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text)


class DayPlanRow(Base):
    __tablename__ = "day_plans"
    __table_args__ = (UniqueConstraint("date", name="uq_day_plans_date"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    date: Mapped[str] = mapped_column(Text)
    slots_json: Mapped[str] = mapped_column(Text)


class SessionRow(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    day_plan_id: Mapped[str] = mapped_column(ForeignKey("day_plans.id"), index=True)
    state: Mapped[str] = mapped_column(Text)
    started_at: Mapped[str | None] = mapped_column(Text)
    settings_json: Mapped[str] = mapped_column(Text)
    stop_reason: Mapped[str | None] = mapped_column(Text)
    # E3 restore (spec 03 §6): frozen slots + open-pause anchor. Nullable —
    # legacy rows stay NULL and are swept instead of restored.
    slots_json: Mapped[str | None] = mapped_column(Text)
    pause_started_at: Mapped[str | None] = mapped_column(Text)


class SegmentRow(Base):
    __tablename__ = "segments"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), index=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"))
    phase: Mapped[str] = mapped_column(Text)
    planned_min: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[str | None] = mapped_column(Text)
    ended_at: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text)
    # E3 restore: wall time frozen by pauses while this segment was open.
    paused_sec: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class ReviewRow(Base):
    __tablename__ = "reviews"

    segment_id: Mapped[str] = mapped_column(ForeignKey("segments.id"), primary_key=True)
    score: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(Text)
    recall_notes: Mapped[str | None] = mapped_column(Text)
    reward: Mapped[str | None] = mapped_column(Text)


class RepetitionRow(Base):
    __tablename__ = "repetitions"

    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), primary_key=True)
    interval_idx: Mapped[int] = mapped_column(Integer)
    next_due: Mapped[str] = mapped_column(Text)


class SettingRow(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text)
