/**
 * Day planner as a pure projection (spec 03 §2 «слоты через PUT day-plan»).
 *
 * Author's funnel law (2026-09-06): backlog = "what must be done at all",
 * planned = distributed over the sprint horizon, DOING = today = the dial.
 * One honest rule keeps the UI simple: the day plan is DERIVED from the
 * «В работе» column — each doing task occupies estimate_blocks consecutive
 * sectors in created order. +/− on a card edits the estimate, the plan PUTs
 * itself. V10 (used ≤ estimate) holds by construction; V9 forbids an empty
 * plan, so a zero-slot derivation is a "do not PUT" signal, never a 422.
 */

import type { SlotDto, TaskDto } from "@/api/client";

export const MAX_PLAN_SLOTS = 12; // core MAX_SECTOR

/** Sector slots for today from the doing column, capped at the dial.
 * DF13 (spec 06): no-timer errands sit in the column for tracking only —
 * the dial and its sectors are timer work, so they never occupy one.
 * DF4-lite (author 08.09): `savedOrder` (task ids in stored-plan sector
 * order) pins the sequence — chunks travel as blocks, unknown or gone
 * ids drop out, fresh tasks append at the end in column order. */
export function deriveSlots(
  doing: TaskDto[],
  savedOrder: readonly string[] = [],
  maxSlots: number = MAX_PLAN_SLOTS,
): SlotDto[] {
  const byId = new Map(doing.map((task) => [task.id, task]));
  const ordered: TaskDto[] = [];
  for (const id of savedOrder) {
    const task = byId.get(id);
    if (task && !ordered.includes(task)) ordered.push(task);
  }
  for (const task of doing) if (!ordered.includes(task)) ordered.push(task);
  const slots: SlotDto[] = [];
  for (const task of ordered) {
    if (task.no_timer) continue;
    for (let i = 0; i < Math.max(1, task.estimate_blocks); i++) {
      if (slots.length >= Math.min(maxSlots, MAX_PLAN_SLOTS)) return slots;
      slots.push({ sector: slots.length + 1, task_id: task.id });
    }
  }
  return slots;
}

/** Stable plan id for a date; the server keeps the stored id on upsert. */
export function planIdForDate(date: string): string {
  return `plan-${date}`;
}

/** Consecutive same-task sectors form a chunk — the unit arrows move (DF4). */
export function taskGroups(slots: readonly SlotDto[]): { taskId: string; sectors: number }[] {
  const groups: { taskId: string; sectors: number }[] = [];
  for (const slot of slots) {
    const last = groups[groups.length - 1];
    if (last && last.taskId === slot.task_id) last.sectors += 1;
    else groups.push({ taskId: slot.task_id, sectors: 1 });
  }
  return groups;
}

/**
 * Swap the chunk at `group` with its neighbour (`delta` ±1) and renumber.
 * Out of range or edge press → same array back (identity: callers no-op).
 */
export function moveTaskBlock(
  slots: readonly SlotDto[],
  group: number,
  delta: number,
): SlotDto[] {
  const chunks: SlotDto[][] = [];
  for (const slot of slots) {
    const last = chunks[chunks.length - 1];
    const tail = last?.[last.length - 1];
    if (last && tail && tail.task_id === slot.task_id) last.push(slot);
    else chunks.push([slot]);
  }
  const to = group + delta;
  if (group < 0 || to < 0 || group >= chunks.length || to >= chunks.length) return slots as SlotDto[];
  const [moved] = chunks.splice(group, 1);
  chunks.splice(to, 0, moved as SlotDto[]);
  return chunks.flat().map((slot, i) => ({ sector: i + 1, task_id: slot.task_id }));
}
