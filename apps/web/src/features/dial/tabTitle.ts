/**
 * Tab title (spec 07 §1 p.22: the countdown rides the tab title; §10.14:
 * the logic is a pure formatting function under one hook — tests assert
 * the FUNCTION, not the DOM, so e2e expectations never break).
 */

export interface TabTitleInput {
  /** Product name, the idle title. */
  appName: string;
  /** Localized phase word ("Работа", "Перерыв", ...), empty when idle. */
  phaseLabel: string;
  /** Seconds left in the current phase; <= 0 or null means "no countdown". */
  remainingSec: number | null;
}

/** mm:ss from seconds (never hours: a pomodoro phase is an hour at most). */
export function mmss(seconds: number): string {
  const safe = Math.max(0, Math.floor(seconds));
  const m = Math.floor(safe / 60);
  const s = safe % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

/** "Pomotivato · Работа 24:10"; idle -> the bare app name (§10.14). */
export function formatTabTitle({ appName, phaseLabel, remainingSec }: TabTitleInput): string {
  if (!phaseLabel || remainingSec === null || remainingSec < 0) return appName;
  return `${appName} · ${phaseLabel} ${mmss(remainingSec)}`;
}
