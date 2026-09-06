import { describe, expect, it } from "vitest";
import type { TaskDto } from "@/api/client";
import { deriveSlots, MAX_PLAN_SLOTS, planIdForDate } from "./planner";

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
});

describe("planIdForDate", () => {
  it("is stable for a given date (server keeps the stored id on upsert)", () => {
    expect(planIdForDate("2026-09-05")).toBe(planIdForDate("2026-09-05"));
    expect(planIdForDate("2026-09-05")).toContain("2026-09-05");
  });
});
