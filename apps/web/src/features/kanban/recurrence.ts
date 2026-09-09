/**
 * Sprint-day recurrence checkboxes (spec 06 DF8–11): pure logic behind the
 * card panel's date row, kept out of the component so the tick→recurrence
 * mapping is Vitest-coverable without DOM (board.ts precedent).
 *
 * The author's model (08.09): no recurrence formulas in the UI — you tick
 * the days in the active sprint the card should be worked on. Ticking maps
 * to core OnDates; unticking all collapses to Once (a plain single-run
 * card, the honest inverse of "no days chosen").
 */

import type { TaskDto } from "@/api/client";

export type Recurrence = TaskDto["recurrence"];

/** An ISO date is "ticked" iff the card's OnDates carry it. */
export function isTicked(recurrence: Recurrence, iso: string): boolean {
  if (recurrence.kind !== "on_dates") return false;
  const days = (recurrence.days as string[] | undefined) ?? [];
  return days.includes(iso);
}

/** The active-sprint day cells a card may tick (1..14, sorted iso). */
export function sprintDays(active: { start_date: string; end_date: string } | null): string[] {
  if (!active) return [];
  const days: string[] = [];
  const start = Date.parse(`${active.start_date}T00:00:00Z`);
  for (
    let t = start;
    t <= Date.parse(`${active.end_date}T00:00:00Z`) && days.length < 14;
    t += 86_400_000
  ) {
    days.push(new Date(t).toISOString().slice(0, 10));
  }
  return days;
}

/** Toggle one day; last tick removed -> Once (never an empty OnDates). */
export function toggleDay(recurrence: Recurrence, iso: string): Recurrence {
  if (recurrence.kind !== "on_dates") {
    return { kind: "on_dates", days: [iso] };
  }
  const current = new Set((recurrence.days as string[] | undefined) ?? []);
  if (current.has(iso)) current.delete(iso);
  else current.add(iso);
  if (current.size === 0) return { kind: "once" };
  return { kind: "on_dates", days: [...current].sort() };
}

/** DF10/11 "2 of 5": done blocks over total ticks (null -> no dot row). */
export function progressOf(task: TaskDto): { done: number; total: number } | null {
  if (task.no_timer) return null;
  if (task.recurrence.kind !== "on_dates") return null;
  const total = ((task.recurrence.days as string[] | undefined) ?? []).length;
  if (total === 0) return null;
  return { done: Math.min(task.blocks_done ?? 0, total), total };
}
