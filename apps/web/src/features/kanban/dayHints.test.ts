import { describe, expect, it } from "vitest";
import type { TaskDto } from "@/api/client";
import { cardHint, dayTickable, formatCardHint, ruDay, ruDays } from "./dayHints";

/**
 * Pure hint logic of E4c PR 4 (spec 07 §4.7): the selector priority
 * (missed > days-left > all-worked > no-days), the dd.MM wordings and the
 * V21 cell rule. Server truth arrives on the DTO; nothing is re-derived.
 */

function task(overrides: Partial<TaskDto> = {}): TaskDto {
  return {
    id: "t-1",
    title: "Card",
    type: "normal",
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
    sprint_id: null,
    carry_choice: null,
    done_at: null,
    blocks_done: null,
    days_done: null,
    last_worked: null,
    days_missed: null,
    days_left: null,
    closeable: null,
    created_at: "2026-09-03T09:00:00+00:00",
    ...overrides,
  };
}

const ticked = (days: string[]) => ({ kind: "on_dates", days });

describe("cardHint (§4.7 selector)", () => {
  it("a missed tick outranks everything: it is the reason Done is closed", () => {
    const hint = cardHint(
      task({
        recurrence: ticked(["2026-09-03", "2026-09-05"]),
        days_missed: ["2026-09-03"],
        days_left: ["2026-09-05"],
        closeable: false,
      }),
    );
    expect(hint).toEqual({ kind: "missed", days: ["2026-09-03"], closeable: false });
  });

  it("remaining days come next, with the close button when V32 allows", () => {
    const hint = cardHint(
      task({
        recurrence: ticked(["2026-09-04", "2026-09-05"]),
        days_left: ["2026-09-05"],
        closeable: true,
      }),
    );
    expect(hint?.kind).toBe("days-left");
    expect(hint?.closeable).toBe(true);
  });

  it("all ticks spent and work done: the all-worked line offers closing", () => {
    const hint = cardHint(task({ recurrence: ticked(["2026-09-04"]), closeable: true }));
    expect(hint).toEqual({ kind: "all-worked", days: [], closeable: true });
  });

  it("a never-marked card gets the plain 'closes after blocks' line", () => {
    const hint = cardHint(task({ recurrence: { kind: "once" }, closeable: false }));
    expect(hint?.kind).toBe("no-days");
  });

  it("no_timer errands explain nothing (they live outside the day math)", () => {
    expect(cardHint(task({ no_timer: true, days_missed: ["2026-09-03"] }))).toBeNull();
  });

  it("a fully worked multi-day card with nothing left and no work is silent", () => {
    // closeable=false (no finished block) + no left/missed days: the walk
    // still owes blocks; no hint line is honest here.
    expect(cardHint(task({ recurrence: ticked(["2026-09-04"]), closeable: false }))).toBeNull();
  });
});

describe("formatCardHint (wording inputs)", () => {
  it("days-left counts worked as total-minus-left for the RU template", () => {
    const card = task({ recurrence: ticked(["2026-09-04", "2026-09-05", "2026-09-06"]) });
    const hint = cardHint(
      Object.assign(card, { days_left: ["2026-09-06"], closeable: false }),
    )!;
    const line = formatCardHint(card, hint);
    expect(line.key).toBe("task-panel.state-days-left");
    expect(line.params).toEqual({ done: 2, total: 3 });
    expect(line.daysText).toBe("06.09");
  });

  it("missed names its days in dd.MM", () => {
    const card = task({ recurrence: ticked(["2026-09-03", "2026-09-04"]) });
    const line = formatCardHint(card, {
      kind: "missed",
      days: ["2026-09-03", "2026-09-04"],
      closeable: false,
    });
    expect(line.key).toBe("task-panel.state-missed");
    expect(line.daysText).toBe("03.09, 04.09");
  });
});

describe("dayTickable (V21 UI half)", () => {
  it("past days accept existing marks only", () => {
    expect(dayTickable("2026-09-02", "2026-09-03", true)).toBe(true); // keep, un-tick allowed
    expect(dayTickable("2026-09-02", "2026-09-03", false)).toBe(false); // new past mark blocked
    expect(dayTickable("2026-09-03", "2026-09-03", false)).toBe(true); // today is fine
    expect(dayTickable("2026-09-05", "2026-09-03", false)).toBe(true); // future is fine
  });
});

describe("ruDay/ruDays", () => {
  it("formats ISO as dd.MM and joins lists", () => {
    expect(ruDay("2026-10-02")).toBe("02.10");
    expect(ruDays(["2026-10-02", "2026-10-03"])).toBe("02.10, 03.10");
  });
});
