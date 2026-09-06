import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Dial } from "./Dial";

/**
 * Component-level checks of the dial (spec 03 §3 + author's law
 * 2026-09-06): sector count, hand/trail visibility, NO text on the circle
 * except the time, rim = phase fraction, phase token colors. Geometry math
 * itself is covered in geometry.test.ts.
 */

function renderDial(overrides: Partial<Parameters<typeof Dial>[0]> = {}) {
  return render(
    <Dial
      sectors={6}
      phase="work"
      sectorIndex={1}
      sectorFraction={0.5}
      phaseFraction={0.5}
      completedSectors={1}
      remainingSec={600}
      active
      {...overrides}
    />,
  );
}

describe("Dial", () => {
  it("draws one division per sector of the snapshot", () => {
    renderDial();

    expect(screen.getByTestId("dial.sector-1")).toBeInTheDocument();
    expect(screen.getByTestId("dial.sector-6")).toBeInTheDocument();
    expect(screen.queryByTestId("dial.sector-7")).not.toBeInTheDocument();
  });

  it("shows the hand and mm:ss when active", () => {
    renderDial();

    expect(screen.getByTestId("dial.hand")).toBeInTheDocument();
    expect(screen.getByTestId("dial.time-readout")).toHaveTextContent("10:00");
  });

  it("readout sits on the 1st/2nd quarter boundary from the bottom (author)", () => {
    renderDial();

    // viewBox height 320; 75% down = y 240 (below center 160)
    expect(screen.getByTestId("dial.time-readout")).toHaveAttribute("y", "240");
  });

  it("hides the hand and zeros the readout when idle", () => {
    renderDial({ active: false, phase: null, remainingSec: 0 });

    expect(screen.queryByTestId("dial.hand")).not.toBeInTheDocument();
    expect(screen.getByTestId("dial.time-readout")).toHaveTextContent("0:00");
  });

  it("carries no text labels except the time readout (author's law)", () => {
    renderDial();

    const texts = document.querySelectorAll("svg text");
    expect(texts).toHaveLength(1);
    expect(texts[0]).toHaveAttribute("data-testid", "dial.time-readout");
  });

  it("keeps completed work sectors painted (author's law 2026-09-06)", () => {
    renderDial({ completedSectors: 2 });

    expect(screen.getByTestId("dial.sector-done-1")).toBeInTheDocument();
    expect(screen.getByTestId("dial.sector-done-2")).toBeInTheDocument();
    expect(screen.queryByTestId("dial.sector-done-3")).not.toBeInTheDocument();
  });

  it("paints no live trail during breaks (the hand rests at the border)", () => {
    renderDial({ phase: "break", completedSectors: 0 });

    // the only paths are the rim circles' siblings: no wedge trails at all
    expect(document.querySelectorAll("svg path")).toHaveLength(0);
  });

  it("rim dasharray follows the PHASE fraction, not the session", () => {
    renderDial({ phaseFraction: 0.25 });

    const [done] = screen
      .getByTestId("dial.rim")
      .getAttribute("stroke-dasharray")!
      .split(" ")
      .map(Number);
    expect(done).toBeCloseTo(2 * Math.PI * 148 * 0.25);
  });

  it("uses the phase token color for hand and rim", () => {
    renderDial({ phase: "long_break" });

    expect(screen.getByTestId("dial.rim")).toHaveAttribute("stroke", "var(--color-long-break)");
  });
});
