/**
 * Dial geometry — pure math, zero DOM (spec 03 §3: Vitest targets exactly
 * this file). Angles are degrees, 0° at 12 o'clock, growing clockwise.
 *
 * Visual model (author's law, E3): sectors = the day plan's slots (one per
 * task, 1..12); the hand sweeps the CURRENT task's sector and paints a
 * trail behind it; pauses freeze it (server truth: remaining_sec). The
 * rim is a PHASE ring: one full circle per phase (a 25-min work or a
 * 5-min break), colored by the phase, painting nothing behind itself.
 * No text on the dial — the task name lives outside the circle.
 */

export const DIAL_MAX_SECTORS = 12; // core MAX_SECTOR mirror
export type PhaseName = "work" | "break" | "long_break";

export function sectorSpan(sectors: number): number {
  return 360 / clampSectors(sectors);
}

export function clampSectors(sectors: number): number {
  return Math.min(DIAL_MAX_SECTORS, Math.max(1, Math.round(sectors)));
}

/** Angle of the hand: sector index (0-based) + progress within it. */
export function handAngle(sectorIndex: number, fraction: number, sectors: number): number {
  const span = sectorSpan(sectors);
  const clamped = Math.min(1, Math.max(0, fraction));
  return (sectorIndex + clamped) * span;
}

export function polarToCartesian(
  cx: number,
  cy: number,
  r: number,
  angleDeg: number,
): { x: number; y: number } {
  const rad = (angleDeg * Math.PI) / 180;
  return { x: cx + r * Math.sin(rad), y: cy - r * Math.cos(rad) };
}

/** Clockwise arc from angle a0 to a1 (a1 >= a0); "" for a degenerate arc. */
export function arcPath(cx: number, cy: number, r: number, a0: number, a1: number): string {
  const sweep = a1 - a0;
  if (sweep <= 0) return "";
  const p0 = polarToCartesian(cx, cy, r, a0);
  const p1 = polarToCartesian(cx, cy, r, a1);
  const large = sweep > 180 ? 1 : 0;
  return `M ${p0.x} ${p0.y} A ${r} ${r} 0 ${large} 1 ${p1.x} ${p1.y}`;
}

/** Filled wedge (center → arc → center) for the active sector highlight. */
export function wedgePath(cx: number, cy: number, r: number, a0: number, a1: number): string {
  const arc = arcPath(cx, cy, r, a0, a1);
  if (!arc) return "";
  return `M ${cx} ${cy} L ${arc.slice(2)} Z`;
}

/**
 * strokeDasharray for the progress rim on a circle of radius r.
 * fraction 0..1 of the circumference, starting at 12 o'clock (the caller
 * rotates the circle -90° so dashes begin at the top).
 */
export function rimDasharray(r: number, fraction: number): string {
  const circumference = 2 * Math.PI * r;
  const done = circumference * Math.min(1, Math.max(0, fraction));
  return `${done} ${circumference - done}`;
}

/** mm:ss for the big readout (never negative, no hours in a pomodoro). */
export function formatRemaining(sec: number): string {
  const s = Math.max(0, Math.floor(sec));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function phaseColorVar(phase: PhaseName | null): string {
  switch (phase) {
    case "break":
      return "var(--color-break)";
    case "long_break":
      return "var(--color-long-break)";
    default:
      return "var(--color-work)";
  }
}
