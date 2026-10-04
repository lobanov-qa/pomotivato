/**
 * Focus workspace rules, pure (spec 07 §4.4, E4c PR 8): what «Обновить
 * статус» would move, which sprint may start a session, and the sector
 * swap the pre-start arrows perform. Everything here mirrors server law
 * (§5.2/§5.6/V25) so the UI explains itself — the server still re-checks
 * every move (DF19).
 */

import type { SprintDto, TaskDto } from "@/api/client";
import { isTicked } from "./recurrence";

/** §5.2 selection: scope ∩ (backlog|planned) ∩ ticked today ∩ timer. */
export function refreshCandidates(
  tasks: TaskDto[],
  scope: string | null,
  today: string,
): TaskDto[] {
  return tasks.filter(
    (task) =>
      task.sprint_id === scope &&
      (task.status === "backlog" || task.status === "planned") &&
      !task.no_timer &&
      isTicked(task.recurrence, today),
  );
}

/** The numbers the server's V25 text carries, for the RU sentence. */
export function parseOverCount(message: string): { in: number; limit: number; more: number } | null {
  const match = /(\d+) of (\d+) in work, (\d+) more to move/.exec(message);
  if (!match) return null;
  return { in: Number(match[1]), limit: Number(match[2]), more: Number(match[3]) };
}

export type ScopeStart =
  | { kind: "shelf" }
  | { kind: "sprint"; sprint_id: string }
  | { kind: "wrong-sprint"; sprint_id: string };

/** V17 red. 5.6: a session starts in the shelf or in a sprint covering
 * today; any other active sprint explains itself instead of starting. */
export function startScope(sprints: SprintDto[], scope: string | null, today: string): ScopeStart {
  if (scope === null) return { kind: "shelf" };
  const sprint = sprints.find((sp) => sp.id === scope);
  if (!sprint) return { kind: "shelf" }; // vanished selection: start as shelf
  const covers = today >= sprint.start_date && today <= sprint.end_date;
  return covers ? { kind: "sprint", sprint_id: sprint.id } : { kind: "wrong-sprint", sprint_id: sprint.id };
}

/** One-sector move (A, B, A is legal — §4.4): the slot at `index` swaps
 * with its neighbor and sectors renumber densely; a no-op at the edges. */
export function swapSector<T extends { sector: number }>(slots: T[], index: number, dir: -1 | 1): T[] {
  const target = index + dir;
  if (target < 0 || target >= slots.length) return slots;
  const next = [...slots];
  [next[index], next[target]] = [next[target], next[index]];
  return next.map((slot, i) => ({ ...slot, sector: i + 1 }));
}
