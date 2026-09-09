/**
 * Science flags for the kanban card (spec 05 §3.1/§3.9): pure predicates
 * the card renders from. Vitest covers the truth table; no DOM, no fetch.
 */

import type { TaskDto } from "@/api/client";

/** V8 soft mode: planned/doing card without an if–then plan deserves the
 * ring + tooltip. The HARD mode (blocking) is the server's V8 — this is
 * only the glow. DF13: no-timer errands are exempt (no report to feed). */
export function needsWhenThen(
  task: Pick<TaskDto, "status" | "when_then"> & { no_timer?: boolean },
): boolean {
  const scheduled = task.status === "planned" || task.status === "doing";
  return scheduled && !task.no_timer && !(task.when_then ?? "").trim();
}

/** The frog badge lights only the server-computed candidate (GET /api/frog
 * is the one owner of the rule — the client never re-implements it). */
export function isFrogCard(taskId: string, frogId: string | null | undefined): boolean {
  return frogId != null && taskId === frogId;
}
