"""Transport DTOs for the stats snapshot (spec 04 §4.1).

Split out of schemas.py on the 300-line smell threshold. Field names are
the stable wire contract (like /api/status): additive only, removal is a
breaking change.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class StatsPeriodDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    date_from: str = Field(alias="from")
    date_to: str = Field(alias="to")


class StatsTotalsDto(BaseModel):
    blocks_done: int
    focus_min: int
    average_score: float | None
    reviews_count: int
    tasks_done: int
    tasks_total: int


class HeatmapCellDto(BaseModel):
    date: str
    blocks_done: int
    focus_min: int


class StreakDto(BaseModel):
    current: int
    current_started: str | None
    record: int
    record_started: str | None


class FactPointDto(BaseModel):
    task_id: str
    title: str
    estimate: int
    actual: int


class EstimateVsFactDto(BaseModel):
    ratio: float | None
    points: list[FactPointDto]


class QuadrantRowDto(BaseModel):
    key: str
    tasks_done: int
    blocks: int
    average_score: float | None


class GoalDepthRowDto(BaseModel):
    filled_fields: int
    tasks: int
    done_ratio: float


class ParentProgressDto(BaseModel):
    task_id: str
    title: str
    done_children: int
    total_children: int


class ZombieItemDto(BaseModel):
    task_id: str
    title: str
    days_stuck: int


class ZombiesDto(BaseModel):
    count: int
    items: list[ZombieItemDto]


class StatsDto(BaseModel):
    """One-shot dashboard snapshot (spec 04 §4.1); flat sections, additive."""

    period: StatsPeriodDto
    totals: StatsTotalsDto
    heatmap: list[HeatmapCellDto]
    streak: StreakDto
    estimate_vs_fact: EstimateVsFactDto
    quadrants: list[QuadrantRowDto]
    goal_depth: list[GoalDepthRowDto]
    parents: list[ParentProgressDto]
    zombies: ZombiesDto
