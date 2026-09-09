/**
 * Science-flag predicates (spec 05 §3.1/§3.9): truth table of the card
 * decorations — no DOM here, the ring/badge rendering is screen-tested.
 */

import { describe, expect, it } from "vitest";
import { isFrogCard, needsWhenThen } from "./science";

describe("needsWhenThen", () => {
  it("fires only for planned/doing with a blank when_then", () => {
    expect(needsWhenThen({ status: "planned", when_then: null })).toBe(true);
    expect(needsWhenThen({ status: "planned", when_then: "  " })).toBe(true);
    expect(needsWhenThen({ status: "doing", when_then: null })).toBe(true);
    expect(needsWhenThen({ status: "backlog", when_then: null })).toBe(false);
    expect(needsWhenThen({ status: "done", when_then: null })).toBe(false);
  });
  it("stays silent once the plan exists", () => {
    expect(needsWhenThen({ status: "planned", when_then: "если 9:00 → пишу" })).toBe(false);
  });
  it("never rings a no-timer errand (DF13)", () => {
    expect(needsWhenThen({ status: "doing", when_then: null, no_timer: true })).toBe(false);
    expect(needsWhenThen({ status: "planned", when_then: "  ", no_timer: true })).toBe(false);
  });
});

describe("isFrogCard", () => {
  it("lights exactly the server candidate", () => {
    expect(isFrogCard("t-1", "t-1")).toBe(true);
    expect(isFrogCard("t-1", "t-2")).toBe(false);
    expect(isFrogCard("t-1", null)).toBe(false);
    expect(isFrogCard("t-1", undefined)).toBe(false); // still loading
  });
});
