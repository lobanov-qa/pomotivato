import { describe, expect, it } from "vitest";
import type { TaskDto } from "@/api/client";
import { TICK_CLASS, tickStateOf, tickStates } from "./tickStates";

/**
 * Day-tick visual states (spec 07 §4.5): planned/missed/worked circles.
 * The server sends days_missed; the rest is text-ISO arithmetic.
 */

function card(days: string[], missed: string[] = []): TaskDto {
  return {
    id: "t-1",
    title: "Card",
    type: "normal",
    important: false,
    urgent: false,
    status: "doing",
    estimate_blocks: 1,
    recurrence: { kind: "on_dates", days },
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
    days_missed: missed,
    days_left: null,
    closeable: null,
    created_at: "2026-10-01T09:00:00+00:00",
  };
}

describe("tickStates", () => {
  it("sorts days and splits them into worked / missed / planned", () => {
    const result = tickStates(card(["2026-10-05", "2026-10-03", "2026-10-08"], ["2026-10-05"]), "2026-10-06");

    expect(result).toEqual([
      { iso: "2026-10-03", state: "worked" },
      { iso: "2026-10-05", state: "missed" }, // past AND unworked -> the red ring
      { iso: "2026-10-08", state: "planned" },
    ]);
  });

  it("a once-card has no row at all", () => {
    expect(tickStates(card([]), "2026-10-06")).toEqual([]);
  });

  it("today's tick is planned, not worked yet", () => {
    const result = tickStates(card(["2026-10-06"]), "2026-10-06");
    expect(result[0].state).toBe("planned");
  });
});

describe("TICK_CLASS (spec 07 §4.5)", () => {
  it("planned never wears the WORK-phase rose — the author's complaint", () => {
    expect(TICK_CLASS.planned).toContain("day-planned"); // green outline
    expect(TICK_CLASS.planned).not.toContain("border-primary");
    expect(TICK_CLASS.missed).toContain("day-missed"); // red ring, never gray
    expect(TICK_CLASS.missed).not.toContain("gray");
    expect(TICK_CLASS.worked).toContain("bg-day-worked"); // filled accent
  });
});

describe("tickStateOf (panel's single-day painter)", () => {
  it("a past tick in days_missed is missed; the rest splits by the clock", () => {
    expect(tickStateOf("2026-10-04", "2026-10-06", ["2026-10-04"])).toBe("missed");
    expect(tickStateOf("2026-10-04", "2026-10-06", [])).toBe("worked");
    expect(tickStateOf("2026-10-06", "2026-10-06", [])).toBe("planned"); // today: still a plan
    expect(tickStateOf("2026-10-09", "2026-10-06", [])).toBe("planned");
  });
});
