import { describe, expect, it } from "vitest";
import type { SlotDto, TaskDto } from "@/api/client";
import { deriveSlots, MAX_PLAN_SLOTS, moveTaskBlock, planIdForDate, taskGroups } from "./planner";

function doing(id: string, blocks: number): TaskDto {
  return { id, status: "doing", estimate_blocks: blocks } as TaskDto;
}

/**
 * Planner projection (equivalence classes: empty plan, chunked tasks,
 * cap boundary): sectors 1..N contiguous, one task may take several.
 * Source column is «В работе» = today (author's funnel law 2026-09-06).
 */

describe("deriveSlots", () => {
  it("returns no slots for an empty doing column", () => {
    expect(deriveSlots([])).toEqual([]);
  });

  it("expands estimate_blocks into consecutive sectors by task order", () => {
    const slots = deriveSlots([doing("a", 2), doing("b", 1)]);

    expect(slots).toEqual([
      { sector: 1, task_id: "a" },
      { sector: 2, task_id: "a" },
      { sector: 3, task_id: "b" },
    ]);
  });

  it("treats estimate < 1 as a single slot", () => {
    expect(deriveSlots([doing("a", 0)])).toEqual([{ sector: 1, task_id: "a" }]);
  });

  it("caps the day at MAX_PLAN_SLOTS (dial has 12 sectors)", () => {
    const slots = deriveSlots(Array.from({ length: 8 }, (_, i) => doing(`t${i}`, 3)));

    expect(slots).toHaveLength(MAX_PLAN_SLOTS);
    expect(slots.at(-1)).toEqual({ sector: MAX_PLAN_SLOTS, task_id: "t3" });
  });

  it("skips no-timer errands — the dial is timer work (DF13)", () => {
    const errand = { ...doing("e", 2), no_timer: true };
    const slots = deriveSlots([errand, doing("a", 1)]);

    expect(slots).toEqual([{ sector: 1, task_id: "a" }]);
  });
});

describe("planIdForDate", () => {
  it("is stable for a given date (server keeps the stored id on upsert)", () => {
    expect(planIdForDate("2026-09-05")).toBe(planIdForDate("2026-09-05"));
    expect(planIdForDate("2026-09-05")).toContain("2026-09-05");
  });
});

describe("taskGroups / moveTaskBlock (DF4-lite arrows)", () => {
  const s = (sector: number, id: string): SlotDto => ({ sector, task_id: id });

  it("groups consecutive same-task sectors into blocks", () => {
    expect(taskGroups([s(1, "a"), s(2, "a"), s(3, "b")])).toEqual([
      { taskId: "a", sectors: 2 },
      { taskId: "b", sectors: 1 },
    ]);
  });

  it("swaps whole blocks — a 2-sector card moves as one", () => {
    const slots = [s(1, "a"), s(2, "a"), s(3, "b"), s(4, "c")];
    expect(moveTaskBlock(slots, 0, +1).map((x) => x.task_id)).toEqual(["b", "a", "a", "c"]);
    expect(moveTaskBlock(slots, 2, -1).map((x) => x.task_id)).toEqual(["a", "a", "c", "b"]);
  });

  it("renumbers sectors densely after a move", () => {
    const next = moveTaskBlock([s(1, "a"), s(2, "b"), s(3, "b")], 0, +1);
    expect(next.map((x) => x.sector)).toEqual([1, 2, 3]);
  });

  it("edge presses and lone blocks are identity (no request)", () => {
    const slots = [s(1, "a"), s(2, "b")];
    expect(moveTaskBlock(slots, 0, -1)).toBe(slots);
    expect(moveTaskBlock(slots, 1, +1)).toBe(slots);
    expect(moveTaskBlock(slots, 5, +1)).toBe(slots);
  });
});
