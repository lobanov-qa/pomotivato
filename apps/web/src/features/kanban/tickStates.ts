/**
 * Day-tick visual states, pure (spec 07 §4.5, E4c PR 7): one source for
 * how a ticked day looks — planned (future/green), worked (filled accent),
 * missed (past tick without a worked block) and plain future ticks. The
 * server already sends days_missed (V31 blockers); everything else is
 * arithmetic over ISO strings, which sort chronologically as text.
 */

import type { TaskDto } from "@/api/client";

export type TickState = "worked" | "missed" | "planned";

/** §4.5 rendering law, one table: planned = green outline, missed = red
 * ring (never gray — gray already means "inactive"), worked = filled accent.
 * Progress circles and panel day-buttons share it (DRY, three call sites). */
export const TICK_CLASS: Record<TickState, string> = {
  planned: "border-day-planned bg-day-planned/10 text-day-planned",
  missed: "border-day-missed text-day-missed ring-1 ring-day-missed",
  worked: "border-transparent bg-day-worked text-primary-foreground",
};

/** dd.MM label for day rows (shared with the panel's row). */
export function tickStates(task: TaskDto, today: string): { iso: string; state: TickState }[] {
  const days = (task.recurrence.days as string[] | undefined) ?? [];
  const missed = new Set(task.days_missed ?? []);
  return [...days]
    .sort()
    .map((iso) => ({
      iso,
      state: missed.has(iso) ? "missed" : iso < today ? "worked" : "planned",
    }));
}

/** One day's state for row painters (the panel's day-button grid). */
export function tickStateOf(iso: string, today: string, missedDays: readonly string[]): TickState {
  return missedDays.includes(iso) ? "missed" : iso < today ? "worked" : "planned";
}
