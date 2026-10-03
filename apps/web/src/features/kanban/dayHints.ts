/**
 * Card state hints (spec 07 §4.7, E4c PR 4): pure logic that decides what
 * the panel writes ABOVE the day row, so the user learns why a card is not
 * in «Готово» without reading docs. The numbers themselves are server truth
 * (days_missed / days_left / closeable ride the board scan — the panel
 * never re-derives day math here, it only picks a line and words it).
 */

import type { TaskDto } from "@/api/client";
import { type MessageKey } from "@/i18n/ru";

export type HintKind = "days-left" | "all-worked" | "missed" | "no-days";

export interface CardHint {
  kind: HintKind;
  /** ISO days the hint names (rendered dd.MM). */
  days: string[];
  /** V32: the panel may offer "translate to Done" right now. */
  closeable: boolean;
}

export interface HintParams {
  [name: string]: string | number;
}

export interface HintLine {
  key: MessageKey;
  params?: HintParams;
  /** dd.MM list appended after a colon; empty means "no day names". */
  daysText: string;
}

/** dd.MM from ISO, the board's own label form (WeekScreen's ruDay precedent). */
export function ruDay(iso: string): string {
  return `${iso.slice(8)}.${iso.slice(5, 7)}`;
}

export function ruDays(list: readonly string[]): string {
  return list.map(ruDay).join(", ");
}

/**
 * The §4.7 table as a selector. Priority: a missed day explains itself
 * first (it blocks Done), then remaining days, then the all-worked state
 * (where V32 close applies), then the plain "no days marked" line.
 */
export function cardHint(task: TaskDto): CardHint | null {
  if (task.no_timer) return null;
  const missed = task.days_missed ?? [];
  const left = task.days_left ?? [];
  const closeable = task.closeable ?? false;
  if (missed.length > 0) return { kind: "missed", days: missed, closeable: false };
  if (left.length > 0) return { kind: "days-left", days: left, closeable };
  if (closeable) return { kind: "all-worked", days: [], closeable: true };
  if (((task.recurrence.days as string[] | undefined) ?? []).length === 0) {
    return { kind: "no-days", days: [], closeable: false };
  }
  return null;
}

/** The hint as wording inputs. "24.09 добавлен"-style toasts reuse ruDays. */
export function formatCardHint(task: TaskDto, hint: CardHint): HintLine {
  const daysText = ruDays(hint.days);
  const ticked = ((task.recurrence.days as string[] | undefined) ?? []).length;
  switch (hint.kind) {
    case "days-left":
      return {
        key: "task-panel.state-days-left",
        params: { done: ticked - hint.days.length, total: ticked },
        daysText,
      };
    case "missed":
      return { key: "task-panel.state-missed", daysText };
    case "all-worked":
      return { key: "task-panel.state-all-worked", daysText: "" };
    case "no-days":
      return { key: "task-panel.state-no-days", daysText: "" };
  }
}

/** V21 UI half: a day cell is tickable unless it is past and unticked. */
export function dayTickable(iso: string, todayIso: string, ticked: boolean): boolean {
  return ticked || iso >= todayIso;
}
