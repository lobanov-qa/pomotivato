import { describe, expect, it } from "vitest";
import type { SprintDto } from "@/api/client";
import {
  hasUndecidedFate,
  SPRINT_COLOR_COUNT,
  sprintColor,
  sprintColorIdx,
  sprintList,
  sprintOfDay,
  sprintStatusKey,
} from "./colors";

/**
 * Sprint presentation rules, pure (spec 07 §3.1, §4.1, E4c PR 7): color
 * derivation, the day-owner pick, the list selection, the status text.
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

describe("sprintColorIdx (spec 07 §3.1)", () => {
  it("wraps at seven with number one starting the palette", () => {
    expect(sprintColorIdx(1)).toBe(0);
    expect(sprintColorIdx(SPRINT_COLOR_COUNT)).toBe(6);
    expect(sprintColorIdx(8)).toBe(0);
    expect(sprintColorIdx(15)).toBe(0);
  });
});

describe("sprintColor", () => {
  it("active sprints wear their color; planned and completed stay gray", () => {
    expect(sprintColor(sprint({ status: "active" }))).not.toBeNull();
    expect(sprintColor(sprint({ status: "planned" }))).toBeNull();
    expect(sprintColor(sprint({ status: "completed" }))).toBeNull();
  });

  it("the same number always gets the same color pair", () => {
    expect(sprintColor(sprint({ number: 3 }))).toEqual(sprintColor(sprint({ number: 3 })));
  });
});

describe("sprintOfDay (§4.1.2)", () => {
  const active = sprint({ id: "a", number: 2, start_date: "2026-10-05", end_date: "2026-10-12" });
  const planned = sprint({ id: "p", number: 3, status: "planned", start_date: "2026-10-10", end_date: "2026-10-20" });
  const late = sprint({ id: "q", number: 9, start_date: "2026-10-05", end_date: "2026-10-12" });
  const upcomingLegacy = sprint({ id: "u", number: 3, status: "planned", start_date: "2026-10-08", end_date: "2026-10-20" });

  it("a day outside every window has no owner", () => {
    expect(sprintOfDay([active, planned], "2026-11-01")).toBeNull();
  });

  it("active wins over a planned overlap", () => {
    expect(sprintOfDay([planned, active], "2026-10-11")?.id).toBe("a");
  });

  it("legacy planned/planned crossings resolve to the bigger number", () => {
    const plannedLate = { ...late, status: "planned" as const };
    expect(sprintOfDay([upcomingLegacy, plannedLate], "2026-10-09")?.id).toBe("q");
  });
});

describe("sprintList (§4.1.3)", () => {
  const today = "2026-10-05";
  const live = sprint({ id: "cur", start_date: "2026-10-01", end_date: "2026-10-07" });
  const upcoming = sprint({ id: "next", number: 2, status: "planned", start_date: "2026-10-08", end_date: "2026-10-14" });
  const stale = sprint({ id: "gone", number: 3, status: "planned", start_date: "2026-09-01", end_date: "2026-09-05" });

  it("keeps live sprints touching today, drops periods fully behind", () => {
    expect(sprintList([live, upcoming, stale], today).map((sp) => sp.id)).toEqual(["cur", "next"]);
  });

  it("adds exactly one completed special after the live rows", () => {
    const completed = sprint({ id: "old", number: 0, status: "completed", start_date: "2026-09-20", end_date: "2026-09-26" });
    expect(sprintList([live, completed], today).map((sp) => sp.id)).toEqual(["cur", "old"]);
  });

  it("an older sprint with undecided fates outranks the newest clean one", () => {
    const pending = sprint({ id: "p1", number: 4, status: "completed", carry_pending: 2 });
    const clean = sprint({ id: "p2", number: 5, status: "completed", carry_pending: 0 });
    expect(sprintList([live, pending, clean], today).map((sp) => sp.id)).toEqual(["cur", "p1"]);
  });
});

describe("sprintStatusKey + hasUndecidedFate", () => {
  it("running only while active AND covering today (A12)", () => {
    expect(sprintStatusKey(sprint(), "2026-10-05")).toBe("running");
    expect(sprintStatusKey(sprint({ start_date: "2026-10-08" }), "2026-10-05")).toBe("created");
    expect(sprintStatusKey(sprint({ status: "planned" }), "2026-10-05")).toBe("created");
    expect(sprintStatusKey(sprint({ status: "completed" }), "2026-10-05")).toBe("finished");
  });

  it("the badge needs a completed sprint with undecided cards (A40)", () => {
    expect(hasUndecidedFate(sprint({ status: "completed", carry_pending: 1 }))).toBe(true);
    expect(hasUndecidedFate(sprint({ status: "completed", carry_pending: 0 }))).toBe(false);
    expect(hasUndecidedFate(sprint({ status: "active", carry_pending: 3 }))).toBe(false);
  });
});
