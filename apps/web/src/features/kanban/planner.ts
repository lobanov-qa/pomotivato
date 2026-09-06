/**
 * Day planner as a pure projection (spec 03 §2 «слоты через PUT day-plan»).
 *
 * One honest rule keeps the UI simple: the day plan is DERIVED from the
 * «planned» column — each planned task occupies estimate_blocks consecutive
 * sectors in created order. +/− on a card edits the estimate, the plan PUTs
 * itself. V10 (used ≤ estimate) holds by construction; V9 forbids an empty
 * plan, so a zero-slot derivation is a "do not PUT" signal, never a 422.
 */

import type { SlotDto, TaskDto } from "@/api/client";

export const MAX_PLAN_SLOTS = 12; // core MAX_SECTOR

/** Sector slots for today from the planned column, capped at the dial. */
export function deriveSlots(planned: TaskDto[]): SlotDto[] {
  const slots: SlotDto[] = [];
  for (const task of planned) {
    for (let i = 0; i < Math.max(1, task.estimate_blocks); i++) {
      if (slots.length >= MAX_PLAN_SLOTS) return slots;
      slots.push({ sector: slots.length + 1, task_id: task.id });
    }
  }
  return slots;
}

/** Stable plan id for a date; the server keeps the stored id on upsert. */
export function planIdForDate(date: string): string {
  return `plan-${date}`;
}
