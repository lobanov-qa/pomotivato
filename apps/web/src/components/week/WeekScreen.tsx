/**
 * Week browser screen (spec 04 §2, ADR-0003 п.1): read-only day walk.
 * Past days carry the truth, future days carry materialized recurrence —
 * both prebaked by GET /api/week. Planning drags land here only in E4b;
 * this screen owns zero mutations.
 */

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "@/api/client";
import type { WeekDayDto } from "@/api/types_stats";
import { t } from "@/i18n/ru";

import { mondayOf, shiftWeeks } from "@/features/week/dates";

function today(): string {
  return new Date().toLocaleDateString("en-CA");
}

function shortDate(iso: string): string {
  return `${iso.slice(8)}.${iso.slice(5, 7)}`;
}

function weekdayName(index: number): string {
  return t("stats.weekdays").split(",")[index] ?? "";
}

const MAX_BAR_PX = 40;

export function WeekScreen() {
  const [start, setStart] = useState(() => mondayOf(today()));
  const [selected, setSelected] = useState<string | null>(null);
  const { data } = useQuery({
    queryKey: ["week", start],
    queryFn: () => api.getWeek(start, 7),
    staleTime: 30_000, // the window is mostly history; SSE owns the live day
  });

  const selectedDay = data?.items.find((item) => item.date === selected) ?? null;

  return (
    <section className="mx-auto w-full max-w-4xl space-y-4" data-testid="week.screen">
      <header className="flex flex-wrap items-center gap-2">
        <h1 className="mr-auto text-lg font-bold">{t("week.title")}</h1>
        <button
          type="button"
          data-testid="week.prev"
          onClick={() => setStart((value) => shiftWeeks(value, -1))}
          className="rounded-md border bg-card px-3 py-1 text-sm hover:bg-muted"
        >
          {t("week.prev")}
        </button>
        <button
          type="button"
          data-testid="week.today"
          onClick={() => setStart(mondayOf(today()))}
          className="rounded-md border bg-card px-3 py-1 text-sm hover:bg-muted"
        >
          {t("week.today")}
        </button>
        <button
          type="button"
          data-testid="week.next"
          onClick={() => setStart((value) => shiftWeeks(value, 1))}
          className="rounded-md border bg-card px-3 py-1 text-sm hover:bg-muted"
        >
          {t("week.next")}
        </button>
      </header>

      <p className="text-xs text-muted-foreground" data-testid="week.range">
        {data ? `${shortDate(data.start)} — ${shortDate(shiftWeeks(data.start, 1))}` : ""}
      </p>

      {!data ? (
        <div
          className="grid grid-cols-7 gap-2"
          data-testid="week.skeleton"
          aria-hidden="true"
        >
          {Array.from({ length: 7 }, (_, index) => (
            <div key={index} className="h-32 rounded-card border bg-card/40" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-7 gap-2">
          {data.items.map((item) => (
            <DayCell
              key={item.date}
              item={item}
              selected={selected === item.date}
              onSelect={() => setSelected(item.date)}
            />
          ))}
        </div>
      )}

      {selectedDay && <DayDetail item={selectedDay} onClose={() => setSelected(null)} />}
    </section>
  );
}

function DayCell({
  item,
  selected,
  onSelect,
}: {
  item: WeekDayDto;
  selected: boolean;
  onSelect: () => void;
}) {
  const summary = item.summary;
  return (
    <button
      type="button"
      data-testid={`week.day-${item.date}`}
      onClick={onSelect}
      aria-pressed={selected}
      className={
        selected
          ? "flex h-36 flex-col rounded-card border-2 border-primary bg-card p-1 text-left"
          : "flex h-36 flex-col rounded-card border bg-card p-1 text-left hover:bg-muted/50"
      }
    >
      <span className="text-[10px] uppercase text-muted-foreground">
        {weekdayName(item.weekday)}
      </span>
      <span className="text-xs font-semibold tabular-nums">{shortDate(item.date)}</span>
      {item.kind === "past" && summary ? (
        <span className="mt-0.5 text-[10px] tabular-nums text-muted-foreground">
          {summary.blocks_done === 0
            ? t("week.empty-past")
            : `${summary.blocks_done} · ${summary.focus_min}${t("summary.min")}`}
          {summary.blocks_done > 0 && summary.average_score !== null && (
            <> · ★{summary.average_score}</>
          )}
        </span>
      ) : (
        <span className="mt-0.5 flex flex-col gap-0.5 text-[10px] leading-tight">
          {item.planned && item.planned.length > 0 ? (
            item.planned.slice(0, 2).map((task) => (
              <span key={task.task_id} className="truncate">
                {task.title}
              </span>
            ))
          ) : (
            <span className="text-muted-foreground">{t("week.empty-future")}</span>
          )}
        </span>
      )}
      <span className="mt-auto flex items-end gap-0.5" aria-hidden="true">
        <span
          className="w-full rounded-sm bg-primary/70"
          style={{ height: `${Math.min(MAX_BAR_PX, 2 + item.volume * 6)}px` }}
        />
      </span>
    </button>
  );
}

function DayDetail({ item, onClose }: { item: WeekDayDto; onClose: () => void }) {
  return (
    <section
      className="rounded-card border bg-card p-4 shadow-card"
      data-testid="week.detail"
    >
      <div className="mb-2 flex items-center gap-2">
        <h2 className="mr-auto text-sm font-semibold">
          {weekdayName(item.weekday)}, {shortDate(item.date)}
        </h2>
        <button
          type="button"
          data-testid="week.detail-close"
          onClick={onClose}
          className="rounded-md px-2 py-0.5 text-xs text-muted-foreground hover:bg-muted"
        >
          ✕
        </button>
      </div>
      {item.kind === "past" && item.summary && (
        <p className="mb-2 text-xs text-muted-foreground tabular-nums">
          {item.summary.blocks_done} {t("stats.blocks")} · {item.summary.focus_min}{" "}
          {t("stats.minutes")}
          {item.summary.average_score !== null && ` · ${t("dial.average-score")}: ${item.summary.average_score}`}
        </p>
      )}
      {item.slots && item.slots.length > 0 && (
        <ul className="space-y-1">
          {item.slots.map((slot) => (
            <li
              key={slot.sector}
              data-testid={`week.slot-${slot.sector}`}
              className="flex items-center gap-2 text-sm"
            >
              <span className="w-6 shrink-0 tabular-nums text-muted-foreground">
                {slot.sector}
              </span>
              <span className="truncate">{slot.task_title}</span>
              {slot.last_score !== null && (
                <span className="ml-auto shrink-0 tabular-nums text-xs text-warning">
                  ★{slot.last_score}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      {item.planned && item.planned.length > 0 && (
        <ul className="space-y-1">
          {item.planned.map((task) => (
            <li key={task.task_id} className="flex items-center gap-2 text-sm">
              <span className="truncate">{task.title}</span>
            </li>
          ))}
        </ul>
      )}
      {item.kind === "future" && (!item.planned || item.planned.length === 0) && (
        <p className="text-sm text-muted-foreground">{t("week.empty-future")}</p>
      )}
    </section>
  );
}
