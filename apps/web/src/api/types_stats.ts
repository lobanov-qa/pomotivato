/**
 * Stats/week wire types (spec 04 §4.1/§4.2), split out of client.ts on the
 * 300-line smell threshold. Shapes mirror api/schemas_stats.py 1:1; the
 * server owns every number — these interfaces carry results, not rules.
 */

import type { DayPlanDto, TaskType } from "./client";

export interface StatsPeriodDto {
  from: string;
  to: string;
}

export interface StatsTotalsDto {
  blocks_done: number;
  focus_min: number;
  average_score: number | null;
  reviews_count: number;
  tasks_done: number;
  tasks_total: number;
}

export interface HeatmapCellDto {
  date: string;
  blocks_done: number;
  focus_min: number;
}

export interface StreakDto {
  current: number;
  current_started: string | null;
  record: number;
  record_started: string | null;
}

export interface FactPointDto {
  task_id: string;
  title: string;
  estimate: number;
  actual: number;
}

export interface EstimateVsFactDto {
  ratio: number | null;
  points: FactPointDto[];
}

export type QuadrantKey =
  | "important_urgent"
  | "important_not_urgent"
  | "urgent_not_important"
  | "neither";

export interface QuadrantRowDto {
  key: QuadrantKey;
  tasks_done: number;
  blocks: number;
  average_score: number | null;
}

export interface GoalDepthRowDto {
  filled_fields: number;
  tasks: number;
  done_ratio: number;
}

export interface ParentProgressDto {
  task_id: string;
  title: string;
  done_children: number;
  total_children: number;
}

export interface ZombieItemDto {
  task_id: string;
  title: string;
  days_stuck: number;
}

export interface ZombiesDto {
  count: number;
  items: ZombieItemDto[];
}

export interface StatsDto {
  period: StatsPeriodDto;
  totals: StatsTotalsDto;
  heatmap: HeatmapCellDto[];
  streak: StreakDto;
  estimate_vs_fact: EstimateVsFactDto;
  quadrants: QuadrantRowDto[];
  goal_depth: GoalDepthRowDto[];
  parents: ParentProgressDto[];
  zombies: ZombiesDto;
}

/** kind is the discriminator (spec 04 §4.2); inactive sections answer null. */
export interface DaySummaryDto {
  blocks_done: number;
  focus_min: number;
  average_score: number | null;
  tasks_done: number;
}

export interface DaySlotDto {
  sector: number;
  task_id: string;
  task_title: string;
  status: string;
  last_score: number | null;
}

export interface PlannedDto {
  task_id: string;
  title: string;
  type: TaskType;
}

/** Sprint wire mirror (spec 05 §3.10, ADR-0003 p.3). */
export interface SprintDto {
  id: string;
  number: number;
  name: string | null;
  start_date: string;
  end_date: string;
  goal: string | null;
  done_criteria: string | null;
  status: "planned" | "active" | "completed";
}

/** add/activate outcome: honest plan + who got in / squeezed out (§3.8). */
export interface AddResultDto {
  plan: DayPlanDto;
  added: string[];
  skipped: string[];
}

export interface WeekDayDto {
  date: string;
  weekday: number;
  kind: "past" | "future";
  summary: DaySummaryDto | null;
  slots: DaySlotDto[] | null;
  planned: PlannedDto[] | null;
  slots_count: number | null;
  volume: number;
}

export interface WeekDto {
  start: string;
  days: number;
  items: WeekDayDto[];
}

/** Labels injected by the screen (dictionary stays the single copy owner;
 * chart builders are pure and locale-agnostic). */
export interface ChartLabels {
  blocks: string;
  minutes: string;
  estimate: string;
  actual: string;
  tasks: string;
  doneRatio: string;
  weekdays: string[];
  months: string[];
}
