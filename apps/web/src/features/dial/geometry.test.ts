import { describe, expect, it } from "vitest";
import {
  arcPath,
  clampSectors,
  DIAL_MAX_SECTORS,
  formatRemaining,
  handAngle,
  phaseColorVar,
  polarToCartesian,
  rimDasharray,
  sectorSpan,
  wedgePath,
} from "./geometry";

/**
 * Geometry is the one frontend module spec 03 §3 demands unit coverage
 * for. Test design: boundary values (0/1 fractions, sector clamps),
 * known-angle identities, and the rim = one phase revolution.
 */

describe("sector math", () => {
  it("six sectors span 60 degrees each", () => {
    expect(sectorSpan(6)).toBeCloseTo(60);
  });

  it("clamps sectors to 1..12 (core MAX_SECTOR mirror)", () => {
    expect(clampSectors(0)).toBe(1);
    expect(clampSectors(13)).toBe(DIAL_MAX_SECTORS);
    expect(clampSectors(6.4)).toBe(6);
  });

  it("hand starts at a sector border and ends at the next", () => {
    expect(handAngle(0, 0, 6)).toBeCloseTo(0);
    expect(handAngle(0, 1, 6)).toBeCloseTo(60);
    expect(handAngle(2, 0.5, 6)).toBeCloseTo(150);
  });

  it("clamps fractions outside 0..1 (stale events cannot overshoot)", () => {
    expect(handAngle(1, -0.5, 4)).toBeCloseTo(90);
    expect(handAngle(1, 1.5, 4)).toBeCloseTo(180);
  });
});

describe("polar & paths", () => {
  it("0 degrees is 12 o'clock and clockwise grows x", () => {
    const top = polarToCartesian(100, 100, 50, 0);
    const right = polarToCartesian(100, 100, 50, 90);
    expect(top.x).toBeCloseTo(100);
    expect(top.y).toBeCloseTo(50);
    expect(right.x).toBeCloseTo(150);
    expect(right.y).toBeCloseTo(100);
  });

  it("arc sweep >180 sets the large-arc flag", () => {
    expect(arcPath(100, 100, 50, 0, 200)).toContain(" 1 1 ");
    expect(arcPath(100, 100, 50, 0, 100)).toContain(" 0 1 ");
  });

  it("degenerate arcs render nothing (zero-progress trail is invisible)", () => {
    expect(arcPath(100, 100, 50, 45, 45)).toBe("");
    expect(wedgePath(100, 100, 50, 45, 45)).toBe("");
  });

  it("wedge closes back to the center", () => {
    const d = wedgePath(100, 100, 50, 0, 30);
    expect(d.startsWith("M 100 100 L ")).toBe(true);
    expect(d.endsWith(" Z")).toBe(true);
  });
});

describe("rim (phase ring: one full circle per phase)", () => {
  it("dasharray splits the circumference at the phase fraction", () => {
    const r = 100;
    const circumference = 2 * Math.PI * r;
    const [done, rest] = rimDasharray(r, 0.25).split(" ").map(Number);
    expect(done).toBeCloseTo(circumference * 0.25);
    expect(done + rest).toBeCloseTo(circumference);
  });

  it("phase start is empty and phase end is the full circle", () => {
    expect(rimDasharray(50, 0).startsWith("0 ")).toBe(true);
    const [done] = rimDasharray(50, 1).split(" ").map(Number);
    expect(done).toBeCloseTo(2 * Math.PI * 50);
  });

  it("fractions outside 0..1 are clamped", () => {
    expect(rimDasharray(50, -1)).toBe(rimDasharray(50, 0));
    expect(rimDasharray(50, 5)).toBe(rimDasharray(50, 1));
  });
});

describe("display helpers", () => {
  it("mm:ss pads seconds and floors", () => {
    expect(formatRemaining(605)).toBe("10:05");
    expect(formatRemaining(0)).toBe("0:00");
    expect(formatRemaining(-3)).toBe("0:00");
  });

  it("phase colors map onto the shared token palette", () => {
    expect(phaseColorVar("work")).toBe("var(--color-work)");
    expect(phaseColorVar("break")).toBe("var(--color-break)");
    expect(phaseColorVar("long_break")).toBe("var(--color-long-break)");
    expect(phaseColorVar(null)).toBe("var(--color-work)");
  });
});
