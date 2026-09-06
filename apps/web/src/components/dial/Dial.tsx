/**
 * The dial: own SVG, no chart libraries (spec 03 §3). Sectors = the
 * session's frozen slots (author's visual law: one division per task);
 * the hand sweeps the current task's sector painting a wedge trail;
 * paused = frozen (server truth, never extrapolated).
 *
 * Author's law (2026-09-06, after the first live review):
 * - NO text on the dial itself (no phase labels, no truncated sector
 *   titles) — the current task name is shown in FULL outside the circle,
 *   with a sector legend so it is obvious which tasks the dial holds;
 * - the rim is a phase ring: one full circle per phase (25-min work ->
 *   one revolution, 5-min break -> one revolution), painting nothing
 *   behind itself. It is NOT a whole-session progress bar.
 *
 * Colors come from the shared token palette so the dial and the app are
 * one design language (minimalist base, skins/themes arrive later).
 */

import type { PhaseName } from "@/features/dial/geometry";
import {
  clampSectors,
  formatRemaining,
  handAngle,
  phaseColorVar,
  polarToCartesian,
  rimDasharray,
  sectorSpan,
  wedgePath,
} from "@/features/dial/geometry";
import { t } from "@/i18n/ru";

const SIZE = 320;
const C = SIZE / 2;
const R_SECTOR = 128; // sector ring radius
const R_RIM = 148; // phase rim radius
const R_HAND = 108;
// Author's law 2026-09-06: the digital readout sits on the boundary of the
// 1st/2nd quarter counted from the bottom — 75% of the dial's height.
const TIME_Y = SIZE * 0.75;

interface Props {
  sectors: number;
  phase: PhaseName | null;
  /** 0-based index of the sector the hand works on. */
  sectorIndex: number;
  /** 0..1 progress inside that sector (frozen while paused). */
  sectorFraction: number;
  /** 0..1 progress of the CURRENT PHASE — the rim's one revolution. */
  phaseFraction: number;
  /** Closed work sectors: their wedges stay painted (author's law). */
  completedSectors: number;
  remainingSec: number;
  active: boolean;
}

export function Dial({
  sectors,
  phase,
  sectorIndex,
  sectorFraction,
  phaseFraction,
  completedSectors,
  remainingSec,
  active,
}: Props) {
  const shown = sectors <= 0 ? 0 : clampSectors(sectors);
  const span = sectorSpan(shown);
  const isWork = phase === "work";
  const color = phaseColorVar(phase);

  const angle = active ? handAngle(sectorIndex, sectorFraction, shown) : 0;
  const handPoint = polarToCartesian(C, C, R_HAND, angle);
  const trailFrom = sectorIndex * span;
  const trail =
    active && isWork && angle > trailFrom ? wedgePath(C, C, R_SECTOR, trailFrom, angle) : "";

  return (
    <svg
      viewBox={`0 0 ${SIZE} ${SIZE}`}
      className="h-full w-full max-w-[360px]"
      role="img"
      aria-label={t("dial.aria")}
      data-testid="dial.root"
    >
      <circle cx={C} cy={C} r={R_SECTOR} fill="none" stroke="var(--color-border)" />
      {Array.from({ length: shown }, (_, i) => {
        const a = i * span;
        const outer = polarToCartesian(C, C, R_SECTOR + 8, a);
        const inner = polarToCartesian(C, C, R_SECTOR - 14, a);
        const isActive = active && i === sectorIndex;
        return (
          <g key={i} data-testid={`dial.sector-${i + 1}`}>
            <line
              x1={inner.x}
              y1={inner.y}
              x2={outer.x}
              y2={outer.y}
              stroke={isActive ? color : "var(--color-border)"}
              strokeWidth={isActive ? 2 : 1}
            />
          </g>
        );
      })}
      {trail && <path d={trail} fill={color} opacity={0.22} />}
      {/* completed work sectors keep their fill (author's law 2026-09-06):
          the dial remembers what the session already did */}
      {Array.from({ length: Math.min(shown, Math.max(0, completedSectors)) }, (_, i) => (
        <path
          key={`done-${i}`}
          d={wedgePath(C, C, R_SECTOR, i * span, (i + 1) * span)}
          fill="var(--color-work)"
          opacity={0.22}
          data-testid={`dial.sector-done-${i + 1}`}
        />
      ))}
      <circle
        cx={C}
        cy={C}
        r={R_RIM}
        fill="none"
        stroke="var(--color-border)"
        strokeWidth={3}
        opacity={0.35}
      />
      <circle
        cx={C}
        cy={C}
        r={R_RIM}
        fill="none"
        stroke={color}
        strokeWidth={3}
        strokeLinecap="round"
        strokeDasharray={rimDasharray(R_RIM, phaseFraction)}
        transform={`rotate(-90 ${C} ${C})`}
        data-testid="dial.rim"
      />
      {active && (
        <g data-testid="dial.hand">
          <line
            x1={C}
            y1={C}
            x2={handPoint.x}
            y2={handPoint.y}
            stroke={color}
            strokeWidth={3}
            strokeLinecap="round"
          />
          <circle cx={handPoint.x} cy={handPoint.y} r={4} fill={color} />
        </g>
      )}
      <circle cx={C} cy={C} r={6} fill="var(--color-foreground)" />
      <text
        x={C}
        y={TIME_Y}
        textAnchor="middle"
        dominantBaseline="middle"
        fontSize={34}
        fontWeight={600}
        fill="var(--color-foreground)"
        data-testid="dial.time-readout"
      >
        {formatRemaining(active ? remainingSec : 0)}
      </text>
    </svg>
  );
}
