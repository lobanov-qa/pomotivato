import { describe, expect, it } from "vitest";
import type { TaskDto } from "@/api/client";
import { applyMove, BOARD_COLUMNS, canDrop, columnOf, dropTarget } from "./board";

/**
 * Board rules (spec 03 §2 + V7 mirror): test design — decision table over
 * the 5x4 status matrix plus the optimistic move primitives.
 */

function task(overrides: Partial<TaskDto> = {}): TaskDto {
  return {
    id: "t-1",
    title: "Some work",
    type: "normal",
    important: false,
    urgent: false,
    status: "backlog",
    estimate_blocks: 1,
    recurrence: { kind: "once" },
    deadline: null,
    parent_id: null,
    when_then: null,
    done_criteria: null,
    benefit: null,
    created_at: "2026-09-05T09:00:00+00:00",
    ...overrides,
  };
}

describe("canDrop (V7 mirror for the drag affordance)", () => {
  it.each([
    ["backlog", "planned", true],
    ["backlog", "doing", false],
    ["backlog", "done", false],
    ["planned", "doing", true],
    ["planned", "backlog", true],
    ["planned", "done", false],
    ["doing", "done", true],
    ["doing", "planned", true],
    ["done", "doing", true],
    ["done", "backlog", false],
  ] as const)("allows %s -> %s = %s", (from, to, expected) => {
    expect(canDrop(from, to)).toBe(expected);
  });
});

describe("dropTarget", () => {
  it("is null for a same-column drop (no request)", () => {
    expect(dropTarget("planned", "planned")).toBeNull();
  });

  it("is null for illegal transitions", () => {
    expect(dropTarget("backlog", "done")).toBeNull();
  });

  it("returns the target for legal transitions", () => {
    expect(dropTarget("doing", "done")).toBe("done");
  });
});

describe("optimistic move", () => {
  it("changes only the moved task and keeps array order", () => {
    const tasks = [task({ id: "a" }), task({ id: "b", status: "planned" })];

    const after = applyMove(tasks, "a", "planned");

    expect(after.map((t) => t.id)).toEqual(["a", "b"]);
    expect(after[0].status).toBe("planned");
    expect(tasks[0].status).toBe("backlog"); // original untouched (immutability)
  });

  it("groups tasks per column in board order", () => {
    const tasks = [
      task({ id: "a", status: "backlog" }),
      task({ id: "b", status: "planned" }),
      task({ id: "c", status: "backlog" }),
    ];

    expect(columnOf(tasks, "backlog").map((t) => t.id)).toEqual(["a", "c"]);
    expect(columnOf(tasks, "doing")).toEqual([]);
  });

  it("archived cards are invisible on the board", () => {
    const tasks = [task({ id: "x", status: "archived" })];

    for (const column of BOARD_COLUMNS) {
      expect(columnOf(tasks, column)).toEqual([]);
    }
  });
});
