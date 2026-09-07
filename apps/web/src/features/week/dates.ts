/**
 * Pure date helpers for the week browser (spec 04 §4.2). Vitest without
 * DOM — dial geometry precedent. Local calendar dates as YYYY-MM-DD; the
 * week window is Monday-based (ADR-0003 rejected ISO-week only because
 * sprints start on arbitrary days, but the browser opens on Monday).
 */

const DAY_MS = 86_400_000;

/** Monday (ISO) of the week containing the given local date. */
export function mondayOf(iso: string): string {
  const day = new Date(`${iso}T00:00:00Z`);
  const shifted = day.getTime() - ((day.getUTCDay() + 6) % 7) * DAY_MS;
  return new Date(shifted).toISOString().slice(0, 10);
}

/** Move a window by `weeks` whole weeks (prev/next buttons). */
export function shiftWeeks(iso: string, weeks: number): string {
  return new Date(Date.parse(`${iso}T00:00:00Z`) + weeks * 7 * DAY_MS)
    .toISOString()
    .slice(0, 10);
}
