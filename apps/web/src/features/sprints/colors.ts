/**
 * Sprint presentation rules, pure (spec 07 §3.1, §4.1, E4c PR 7):
 * the color is derived, never stored — color_idx = (number - 1) % 7, and
 * the number only ever grows, so a card keeps its color for life.
 * The list rules (§4.1.3): today's planned+active sprints plus exactly
 * one newest special (completed with a fate still open, or completed).
 */

import type { SprintDto } from "@/api/client";

export const SPRINT_COLOR_COUNT = 7;

/** Tailwind color index 0..6 for a sprint number (1-based, stable). */
export function sprintColorIdx(number: number): number {
  return (number - 1) % SPRINT_COLOR_COUNT;
}

/** Tailwind-ready class pair: border + 8-12% fill (spec 07 §4.1.2). */
export const SPRINT_COLOR_CLASSES: readonly { border: string; fill: string }[] = [
  { border: "border-sprint-0", fill: "bg-sprint-0/10" },
  { border: "border-sprint-1", fill: "bg-sprint-1/10" },
  { border: "border-sprint-2", fill: "bg-sprint-2/10" },
  { border: "border-sprint-3", fill: "bg-sprint-3/10" },
  { border: "border-sprint-4", fill: "bg-sprint-4/10" },
  { border: "border-sprint-5", fill: "bg-sprint-5/10" },
  { border: "border-sprint-6", fill: "bg-sprint-6/10" },
];

export function sprintColor(sprint: Pick<SprintDto, "number" | "status">) {
  // Planned and completed stay gray (§4.1.1); only active sprints wear color.
  if (sprint.status !== "active") return null;
  return SPRINT_COLOR_CLASSES[sprintColorIdx(sprint.number)];
}

/** Day-cell palette (§4.1.2): a day inside ANY sprint window wears the
 * owner's color — planned windows count as reservations too, so the grid
 * reads "these days are spoken for" before activation. */
export function dayPalette(sprint: Pick<SprintDto, "number">) {
  return SPRINT_COLOR_CLASSES[sprintColorIdx(sprint.number)];
}

/** Whose color is this ISO day? active beats planned; legacy overlaps
 * (§4.1.2: pre-reset data may still cross) resolve to the bigger number. */
export function sprintOfDay(sprints: SprintDto[], iso: string): SprintDto | null {
  const covering = sprints.filter((sp) => iso >= sp.start_date && iso <= sp.end_date);
  if (covering.length === 0) return null;
  const active = covering.filter((sp) => sp.status === "active");
  const pool = active.length > 0 ? active : covering;
  return pool.reduce((best, sp) => (sp.number > best.number ? sp : best));
}

/** §4.1.3: planned+active as of today (dates overlap today or ahead),
 * plus ONE special: the newest completed sprint — shown when it still
 * has an undecided fate ("!") or as the most recent closed chapter. */
export function sprintList(sprints: SprintDto[], todayIso: string): SprintDto[] {
  const live = sprints
    .filter((sp) => sp.status !== "completed" && sp.end_date >= todayIso)
    .sort((a, b) => a.number - b.number);
  const completed = sprints
    .filter((sp) => sp.status === "completed")
    .sort((a, b) => b.number - a.number);
  // The one special: newest UNDECIDED first (a "!" must never hide behind a
  // clean newest chapter), else simply the newest completed one.
  const special = completed.find(hasUndecidedFate) ?? completed[0];
  return special ? [...live, special] : live;
}

/** Text status marker out of status + today-in-period (§3.1, A12). */
export function sprintStatusKey(sprint: SprintDto, todayIso: string): "created" | "running" | "finished" {
  if (sprint.status === "planned") return "created";
  if (sprint.status === "completed") return "finished";
  return todayIso >= sprint.start_date && todayIso <= sprint.end_date ? "running" : "created";
}

/** The "!" badge: completed, unfinished cards exist and no fate chosen (A40). */
export function hasUndecidedFate(sprint: SprintDto): boolean {
  return sprint.status === "completed" && sprint.carry_pending > 0;
}
