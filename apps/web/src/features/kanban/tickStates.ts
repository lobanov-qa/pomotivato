/**
 * Day-tick visual states, pure (spec 07 §4.5, E4c PR 7): one source for
 * how a ticked day looks — planned (future/green), worked (filled accent),
 * missed (past tick without a worked block) and plain future ticks. The
 * server already sends days_missed (V31 blockers); everything else is
 * arithmetic over ISO strings, which sort chronologically as text.
 */

import type { TaskDto } from "@/api/client";

export type TickState = "worked" | "missed" | "planned";

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
