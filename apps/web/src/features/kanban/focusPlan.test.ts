import { describe, expect, it } from "vitest";
import type { SprintDto, TaskDto } from "@/api/client";
import { parseOverCount, refreshCandidates, startScope, swapSector } from "./focusPlan";

/**
 * Focus workspace rules, pure (spec 07 §4.4/§5.2, E4c PR 8): the A4
 * candidate pick, the V25 number extraction, the V17 start scope and the
 * one-sector arrow swap.
 */

function sprint(overrides: Partial<SprintDto> = {}): SprintDto {
  return {
    id: "s-1",
    number: 1,
    name: null,
    start_date: "2026-10-01",
    end_date: "2026-10-07",
    goal: null,
    done_criteria: null,
    status: "active",
    unfinished_count: 0,
    carry_pending: 0,
    is_current: true,
    ...overrides,
  };
}

function task(overrides: Partial<TaskDto> = {}): TaskDto {
  return {
    id: "t-1",
    title: "Card",
    type: "normal",
    important: false,
    urgent: false,
    status: "backlog",
    estimate_blocks: 1,
    recurrence: { kind: "on_dates", days: ["2026-10-05"] },
    deadline: null,
    parent_id: null,
    when_then: null,
    done_criteria: null,
    benefit: null,
    cloned_from: null,
    no_timer: false,
    sprint_id: "s-1",
    carry_choice: null,
    done_at: null,
    blocks_done: null,
    days_done: null,
    last_worked: null,
    days_missed: null,
    days_left: null,
    closeable: null,
    created_at: "2026-10-01T09:00:00+00:00",
    ...overrides,
  };
}

describe("refreshCandidates (§5.2)", () => {
  const today = "2026-10-05";

  it("picks scope cards that are backlog/planned, ticked today and timer-carrying", () => {
    const tasks = [
      task({ id: "ok-back" }),
      task({ id: "ok-plan", status: "planned" }),
      task({ id: "wrong-scope", sprint_id: "s-2" }),
      task({ id: "unticked", recurrence: { kind: "once" } }),
      task({ id: "errand", no_timer: true }),
      task({ id: "already-doing", status: "doing" }),
      task({ id: "done-card", status: "done" }),
    ];

    expect(refreshCandidates(tasks, "s-1", today).map((t) => t.id)).toEqual(["ok-back", "ok-plan"]);
  });

  it("the shelf scope only ever sees sprint-less cards", () => {
    const tasks = [task({ id: "shelf", sprint_id: null }), task({ id: "owned" })];
    expect(refreshCandidates(tasks, null, today).map((t) => t.id)).toEqual(["shelf"]);
  });
});

describe("parseOverCount (V25 wire text)", () => {
  it("reads the server numbers back into the RU sentence", () => {
    const parsed = parseOverCount(
      "refresh would exceed the in-work limit: 4 of 4 in work, 2 more to move (2 over)",
    );
    expect(parsed).toEqual({ in: 4, limit: 4, more: 2 });
  });

  it("unrelated texts parse to null (the raw message renders instead)", () => {
    expect(parseOverCount("no task in progress")).toBeNull();
  });
});

describe("startScope (V17 red. 5.6)", () => {
  const today = "2026-10-05";

  it("the shelf starts on its own", () => {
    expect(startScope([], null, today)).toEqual({ kind: "shelf" });
  });

  it("a sprint covering today may start; one that does not, warns", () => {
    expect(startScope([sprint()], "s-1", today)).toEqual({ kind: "sprint", sprint_id: "s-1" });
    const future = sprint({ id: "s-9", start_date: "2026-11-01", end_date: "2026-11-07" });
    expect(startScope([future], "s-9", today)).toEqual({ kind: "wrong-sprint", sprint_id: "s-9" });
  });

  it("a selection whose sprint vanished behaves like the shelf", () => {
    expect(startScope([sprint()], "ghost", today)).toEqual({ kind: "shelf" });
  });
});

describe("swapSector (§4.4 arrows)", () => {
  const slots = [
    { sector: 1, task_id: "a" },
    { sector: 2, task_id: "b" },
    { sector: 3, task_id: "c" },
  ];

  it("moves one sector and renumbers densely", () => {
    expect(swapSector(slots, 2, -1)).toEqual([
      { sector: 1, task_id: "a" },
      { sector: 2, task_id: "c" },
      { sector: 3, task_id: "b" },
    ]);
  });

  it("edges are a no-op (nothing wraps around)", () => {
    expect(swapSector(slots, 0, -1)).toEqual(slots);
    expect(swapSector(slots, 2, 1)).toEqual(slots);
  });
});
