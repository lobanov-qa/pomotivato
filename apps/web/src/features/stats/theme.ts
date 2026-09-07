/**
 * ECharts palette from the live CSS custom properties (spec 04 §5).
 *
 * The theme switcher owns only index.css variables; charts must follow it
 * without knowing about dark/light at all — getComputedStyle is the single
 * source, so a re-paint reads fresh values. No chart library re-theming.
 */

export interface ChartTheme {
  text: string;
  muted: string;
  border: string;
  card: string;
  work: string;
  break: string;
  accent: string;
}

const FALLBACK: ChartTheme = {
  text: "#18181b",
  muted: "#71717a",
  border: "#e4e4e7",
  card: "#ffffff",
  work: "#e11d48",
  break: "#0d9488",
  accent: "#6366f1",
};

function readVar(element: HTMLElement | null, name: string): string | undefined {
  if (!element) return undefined;
  const value = getComputedStyle(element).getPropertyValue(name).trim();
  return value.length > 0 ? value : undefined;
}

export function chartThemeFrom(root?: HTMLElement | null): ChartTheme {
  const target = root ?? document.documentElement;
  const read = (name: string, fallback: string) => readVar(target, name) ?? fallback;
  return {
    text: read("--color-foreground", FALLBACK.text),
    muted: read("--color-muted-foreground", FALLBACK.muted),
    border: read("--color-border", FALLBACK.border),
    card: read("--color-card", FALLBACK.card),
    work: read("--color-work", FALLBACK.work),
    break: read("--color-break", FALLBACK.break),
    accent: read("--color-long-break", FALLBACK.accent),
  };
}
