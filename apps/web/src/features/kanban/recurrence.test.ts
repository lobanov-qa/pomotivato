import { describe, expect, it } from "vitest";
import type { TaskDto } from "@/api/client";
import { isTicked, progressOf, sprintDays, toggleDay } from "./recurrence";

/**
 * Sprint-day checkbox logic (spec 06 DF8–11): decision table over the
 * tick/untick mapping and the "2 of 5" progress projection.
 */

function task(overrides: Partial<TaskDto> = {}): TaskDto {
  return {
    id: "t-1",
    title: "English",
    type: "study",
    important: false,
    urgent: false,
    status: "planned",
    estimate_blocks: 1,
    recurrence: { kind: "once" },
    deadline: null,
    parent_id: null,
    when_then: null,
    done_criteria: null,
    benefit: null,
    cloned_from: null,
    no_timer: false,
    blocks_done: null,
    days_done: null,
    last_worked: null,
    created_at: "2026-09-08T09:00:00+00:00",
    ...overrides,
  };
}

describe("sprintDays", () => {
  it("lists the active window days, capped at 14", () => {
    const days = sprintDays({ start_date: "2026-09-07", end_date: "2026-09-13" });
    expect(days).toHaveLength(7);
    expect(days[0]).toBe("2026-09-07");
    expect(days.at(-1)).toBe("2026-09-13");
    expect(sprintDays(null)).toEqual([]);
  });
});

describe("isTicked / toggleDay", () => {
  it("first tick turns a single-run card into an on_dates card", () => {
    const next = toggleDay({ kind: "once" }, "2026-09-09");
    expect(next).toEqual({ kind: "on_dates", days: ["2026-09-09"] });
    expect(isTicked(next, "2026-09-09")).toBe(true);
    expect(isTicked(next, "2026-09-10")).toBe(false);
  });

  it("ticking adds and unticking removes, days stay sorted", () => {
    let rec = toggleDay({ kind: "once" }, "2026-09-11");
    rec = toggleDay(rec, "2026-09-09");
    rec = toggleDay(rec, "2026-09-10");
    expect(rec).toEqual({ kind: "on_dates", days: ["2026-09-09", "2026-09-10", "2026-09-11"] });
    rec = toggleDay(rec, "2026-09-10");
    expect(rec.days).toEqual(["2026-09-09", "2026-09-11"]);
  });

  it("the last untick collapses to once, never an empty on_dates", () => {
    const one = { kind: "on_dates", days: ["2026-09-09"] };
    expect(toggleDay(one, "2026-09-09")).toEqual({ kind: "once" });
  });
});

describe("progressOf", () => {
  it("reports worked ticked days over total ticks for a ticked card only", () => {
    const ticked = task({
      recurrence: { kind: "on_dates", days: ["2026-09-09", "2026-09-11"] },
      days_done: 1,
    });
    expect(progressOf(ticked)).toEqual({ done: 1, total: 2 });
    expect(progressOf(task({ recurrence: { kind: "once" } }))).toBeNull();
    expect(progressOf(task({ no_timer: true, days_done: 2 }))).toBeNull();
  });

  it("keeps the block count out of the dots (days are the currency)", () => {
    const ticked = task({
      recurrence: { kind: "on_dates", days: ["2026-09-09"] },
      blocks_done: 4, // two sessions in one day are still one day
      days_done: 1,
    });
    expect(progressOf(ticked)).toEqual({ done: 1, total: 1 });
  });
});
