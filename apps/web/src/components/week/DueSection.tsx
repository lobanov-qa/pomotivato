/**
 * Spaced-repetition inbox on /week (spec 05 §3.7): rows due today or
 * overdue, oldest first (server order). "в план дня" = POST add primitive
 * (chunked, capacity-honest); after it the queue and the task board
 * invalidate — the ladder itself only moves on the next review (E2 rule).
 */

import { useDueRepetitions, useAddDueToToday } from "@/features/science/hooks";
import { t } from "@/i18n/ru";
import { cn } from "@/lib/utils";

export function DueSection() {
  const { data, isPending } = useDueRepetitions();
  const add = useAddDueToToday();

  if (isPending) return null;
  const rows = data ?? [];
  return (
    <section
      className={cn(
        "rounded-card border bg-card p-3",
        rows.length === 0 && "flex items-center gap-2 text-xs text-muted-foreground",
      )}
      data-testid="week.due-section"
    >
      {rows.length === 0 ? (
        <>
          <span className="font-semibold uppercase tracking-wide">{t("week.due-title")}</span>
          <span>· {t("week.due-empty")}</span>
        </>
      ) : (
        <>
          <p className="mb-1 text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
            {t("week.due-title")}
          </p>
          <ul className="flex flex-col gap-1">
            {rows.map((row) => (
              <li
                key={row.task_id}
                data-testid={`week.due-row-${row.task_id}`}
                className="flex items-center gap-2 text-sm"
              >
                <span className="min-w-0 flex-1 truncate">{row.title}</span>
                <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                  {t("week.due-interval")} {row.interval_idx + 1}/5
                  {row.overdue_days > 0 && (
                    <span className="text-warning">
                      {" "}
                      · {t("week.due-overdue")} {row.overdue_days}
                    </span>
                  )}
                </span>
                <button
                  type="button"
                  data-testid={`week.due-add-${row.task_id}`}
                  disabled={add.isPending}
                  onClick={() => add.mutate(row.task_id)}
                  className="shrink-0 rounded-md border border-primary px-2 py-0.5 text-xs text-primary hover:bg-primary/10"
                >
                  {t("week.due-add")}
                </button>
              </li>
            ))}
          </ul>
          {(add.isSuccess || add.isError) && (
            <p
              data-testid="week.due-flash"
              className={cn("mt-1 text-xs", add.isError ? "text-danger" : "text-muted-foreground")}
            >
              {add.isError
                ? t("week.due-skipped")
                : add.data && add.data.added.length === 0
                  ? t("week.due-skipped")
                  : t("week.due-added")}
            </p>
          )}
        </>
      )}
    </section>
  );
}
