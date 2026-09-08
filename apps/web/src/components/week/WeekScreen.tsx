/**
 * Week screen (spec 04 §2 read-only browser + spec 05 §3.8 planning).
 * E4b-UX DF1 (author 08.09): the drag strip left — the kanban is the one
 * place cards get planned; the day panel got a × per slot (DELETE slot)
 * so anything the week holds can be taken off without dragging. Today
 * still offers "activate" for recurring tasks and ↑/↓ reorder (POST
 * slots/move). Past dates stay untouchable (⚑ Q4).
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/api/client";
import type { WeekDayDto } from "@/api/types_stats";
import { DueSection } from "@/components/week/DueSection";
import { SprintBand } from "@/components/week/SprintBand";
import { useSprintDates } from "@/features/sprints/hooks";
import { mondayOf, shiftWeeks } from "@/features/week/dates";
import { t } from "@/i18n/ru";
import { cn } from "@/lib/utils";

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
  const [flash, setFlash] = useState<string | null>(null);
  const client = useQueryClient();
  const { data } = useQuery({
    queryKey: ["week", start],
    queryFn: () => api.getWeek(start, 7),
    staleTime: 30_000, // the window is mostly history; SSE owns the live day
  });
  const inSprint = useSprintDates();

  const selectedDay = data?.items.find((item) => item.date === selected) ?? null;
  const windowDates = data?.items.map((item) => item.date) ?? [];

  const invalidateWeek = () => {
    void client.invalidateQueries({ queryKey: ["week"] });
    void client.invalidateQueries({ queryKey: ["tasks"] });
  };

  const activate = useMutation({
    mutationFn: (date: string) => api.activatePlan(date),
    onSuccess: (result, date) => {
      invalidateWeek();
      setFlash(
        result.added.length > 0
          ? `${shortDate(date)}: ${t("week.activate-done")}` +
            (result.skipped.length ? ` · ${t("week.activate-skipped")}` : "")
          : `${shortDate(date)}: ${t("week.activate-none")}`,
      );
    },
  });

  return (
    <section className="mx-auto w-full max-w-4xl space-y-4" data-testid="week.screen">
      <header className="flex flex-wrap items-center gap-2">
        <h1 className="mr-auto text-lg font-bold">{t("week.title")}</h1>
        {windowDates.includes(today()) && (
          <button
            type="button"
            data-testid="week.activate-today"
            onClick={() => activate.mutate(today())}
            disabled={activate.isPending}
            className="rounded-md border border-primary px-3 py-1 text-sm text-primary hover:bg-primary/10"
          >
            {t("week.activate")}
          </button>
        )}
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

      <SprintBand windowDates={windowDates} />

      <p className="text-xs text-muted-foreground" data-testid="week.range">
        {data ? `${shortDate(data.start)} — ${shortDate(shiftWeeks(data.start, 1))}` : ""}
      </p>

      {!data ? (
        <div className="grid grid-cols-7 gap-2" data-testid="week.skeleton" aria-hidden="true">
          {Array.from({ length: 7 }, (_, index) => (
            <div key={index} className="h-36 rounded-card border bg-card/40" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-7 gap-2">
          {data.items.map((item) => (
            <DayCell
              key={item.date}
              item={item}
              selected={selected === item.date}
              sprintDay={inSprint(item.date)}
              onSelect={() => setSelected(item.date)}
            />
          ))}
        </div>
      )}

      {(flash || activate.isError) && (
        <p
          data-testid="week.flash"
          className={cn("text-xs", activate.isError ? "text-danger" : "text-muted-foreground")}
        >
          {activate.isError ? t("error.unknown") : flash}
        </p>
      )}

      <DueSection />

      {selectedDay && (
        <DayDetail item={selectedDay} onClose={() => setSelected(null)} onChanged={invalidateWeek} />
      )}
    </section>
  );
}

function DayCell({
  item,
  selected,
  sprintDay,
  onSelect,
}: {
  item: WeekDayDto;
  selected: boolean;
  sprintDay: boolean;
  onSelect: () => void;
}) {
  const summary = item.summary;
  return (
    <button
      type="button"
      data-testid={`week.day-${item.date}`}
      onClick={onSelect}
      aria-pressed={selected}
      className={cn(
        "flex h-36 flex-col rounded-card border p-1 text-left",
        selected ? "border-2 border-primary bg-card" : "bg-card hover:bg-muted/50",
        sprintDay && !selected && "border-primary/40",
      )}
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

function DayDetail({
  item,
  onClose,
  onChanged,
}: {
  item: WeekDayDto;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [error, setError] = useState(false);
  const editable = item.date >= today();
  const slotCount = item.slots?.length ?? 0;

  async function move(from: number, to: number): Promise<void> {
    try {
      await api.moveSlot(item.date, from, to);
      setError(false);
      onChanged();
    } catch {
      setError(true);
    }
  }

  /** DF1: take one card off the day; the × must work even on a lone slot. */
  async function remove(sector: number): Promise<void> {
    try {
      await api.removeSlot(item.date, sector);
      setError(false);
      onChanged();
    } catch {
      setError(true);
    }
  }

  return (
    <section className="rounded-card border bg-card p-4 shadow-card" data-testid="week.detail">
      <div className="mb-2 flex items-center gap-2">
        <h2 className="mr-auto text-sm font-semibold">
          {weekdayName(item.weekday)}, {shortDate(item.date)}
        </h2>
        {error && <span className="text-xs text-danger">{t("error.unknown")}</span>}
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
          {item.summary.average_score !== null &&
            ` · ${t("dial.average-score")}: ${item.summary.average_score}`}
        </p>
      )}
      {item.slots && item.slots.length > 0 && (
        <ul className="space-y-1">
          {item.slots.map((slot, index) => (
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
                <span className="tabular-nums text-xs text-warning">★{slot.last_score}</span>
              )}
              {editable && (
                <span className="ml-auto flex shrink-0 gap-1">
                  <button
                    type="button"
                    aria-label={t("week.plan-move-up")}
                    data-testid={`week.slot-move-up-${slot.sector}`}
                    disabled={index === 0 || slotCount <= 1}
                    onClick={() => void move(index + 1, index)}
                    className="rounded px-1 text-xs hover:bg-muted disabled:opacity-30"
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    aria-label={t("week.plan-move-down")}
                    data-testid={`week.slot-move-down-${slot.sector}`}
                    disabled={index === slotCount - 1 || slotCount <= 1}
                    onClick={() => void move(index + 1, index + 2)}
                    className="rounded px-1 text-xs hover:bg-muted disabled:opacity-30"
                  >
                    ↓
                  </button>
                  <button
                    type="button"
                    aria-label={t("week.plan-remove")}
                    data-testid={`week.slot-remove-${slot.sector}`}
                    onClick={() => void remove(slot.sector)}
                    className="rounded px-1 text-xs text-danger hover:bg-muted"
                  >
                    ×
                  </button>
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
