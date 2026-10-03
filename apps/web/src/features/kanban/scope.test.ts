import { describe, expect, it } from "vitest";
import type { SprintDto, TaskDto } from "@/api/client";
import {
  defaultScope,
  scopeFromParam,
  scopeOptions,
  scopeToParam,
  withinScope,
} from "./scope";

/**
 * Board-scope pure logic (spec 07 §4.3, E4c PR 5): what the selector may
 * offer (activated only, A13), how the URL param maps, and which cards a
 * scope shows. The server re-checks membership (V28) — this is view math.
 */

function sprint(overrides: Partial<SprintDto> = {}): SprintDto {
  return {
    id: "s-1",
    number: 1,
    name: "w40",
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
    recurrence: { kind: "once" },
    deadline: null,
    parent_id: null,
    when_then: null,
    done_criteria: null,
    benefit: null,
    cloned_from: null,
    no_timer: false,
    sprint_id: null,
    carry_choice: null,
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

describe("scope params", () => {
  it("the shelf travels as 'none' and back", () => {
    expect(scopeToParam(null)).toBe("none");
    expect(scopeToParam("s-1")).toBe("s-1");
    expect(scopeFromParam("none")).toBeNull();
    expect(scopeFromParam("s-1")).toBe("s-1");
    expect(scopeFromParam(null)).toBeUndefined(); // absent -> fallback
  });
});

describe("scopeOptions (A13)", () => {
  it("lists activated sprints newest-first plus the shelf, never a planned one", () => {
    const options = scopeOptions([
      sprint({ id: "s-2", number: 2, status: "planned" }),
      sprint({ id: "s-1", number: 1 }),
      sprint({ id: "s-3", number: 3, status: "completed" }),
    ]);
    expect(options.map((option) => option.value)).toEqual(["s-1", null]);
    expect(options[0].label).toBe("#1 · w40");
  });
});

describe("defaultScope (§4.3 fallback chain)", () => {
  const sprints = [sprint({ id: "s-1" }), sprint({ id: "s-2", number: 2, status: "planned" })];

  it("prefers a saved choice that still exists", () => {
    expect(defaultScope(sprints, "2026-10-02", "s-1")).toBe("s-1");
    expect(defaultScope(sprints, "2026-10-02", null)).toBeNull(); // shelf sticks too
  });

  it("drops a saved choice when its sprint vanished or was never active", () => {
    expect(defaultScope(sprints, "2026-10-02", "ghost")).toBe("s-1");
    expect(defaultScope(sprints, "2026-10-02", "s-2")).toBe("s-1"); // planned is not selectable
  });

  it("without a choice picks the sprint covering today, else the shelf", () => {
    expect(defaultScope(sprints, "2026-10-02", undefined)).toBe("s-1");
    const future = sprint({ id: "s-9", start_date: "2027-01-01", end_date: "2027-01-07" });
    expect(defaultScope([future], "2026-10-02", undefined)).toBeNull();
    expect(defaultScope([], "2026-10-02", undefined)).toBeNull();
  });
});

describe("withinScope", () => {
  it("a card shows iff its owner equals the scope (shelf = null)", () => {
    const shelf = task();
    const owned = task({ id: "t-2", sprint_id: "s-1" });
    expect(withinScope(shelf, null)).toBe(true);
    expect(withinScope(shelf, "s-1")).toBe(false);
    expect(withinScope(owned, "s-1")).toBe(true);
    expect(withinScope(owned, null)).toBe(false);
  });
});
