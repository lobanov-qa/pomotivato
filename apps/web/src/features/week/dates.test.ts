/** Vitest floor for pure week-date helpers (no DOM, no fetch). */

import { describe, expect, it } from "vitest";

import { mondayOf, shiftWeeks } from "./dates";

describe("mondayOf", () => {
  it("maps any weekday to the Monday of its ISO week", () => {
    expect(mondayOf("2026-09-07")).toBe("2026-09-07"); // Monday
    expect(mondayOf("2026-09-03")).toBe("2026-08-31"); // Thursday -> prev Mon
    expect(mondayOf("2026-09-13")).toBe("2026-09-07"); // Sunday
  });
});

describe("shiftWeeks", () => {
  it("moves whole weeks forward and back", () => {
    expect(shiftWeeks("2026-09-07", 1)).toBe("2026-09-14");
    expect(shiftWeeks("2026-09-07", -1)).toBe("2026-08-31");
  });

  it("crosses month boundaries cleanly", () => {
    expect(shiftWeeks("2026-08-31", 1)).toBe("2026-09-07");
  });
});
