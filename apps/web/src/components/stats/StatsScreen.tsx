/**
 * Dashboard screen (spec 04 §2/§5): every number arrives ready from
 * GET /api/stats — the client only formats (E3 law: no client math).
 * Read-only by the screen law; no task editing here, ever.
 */

import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { api } from "@/api/client";
import { Chart } from "@/features/stats/Chart";
import {
  estimateVsFactOption,
  goalDepthOption,
  heatmapOption,
  quadrantsOption,
} from "@/features/stats/chartOptions";
import { useThemeEpoch } from "@/features/stats/hooks";
import { chartThemeFrom } from "@/features/stats/theme";
import type { ChartLabels, QuadrantKey } from "@/api/types_stats";
import { t, type MessageKey } from "@/i18n/ru";

const DAY_MS = 86_400_000;

/** Local calendar date as YYYY-MM-DD (SummaryPanel precedent). */
function isoDaysAgo(days: number): string {
  return new Date(Date.now() - days * DAY_MS).toLocaleDateString("en-CA");
}

type Period = "week" | "month";

const PERIOD_DAYS: Record<Period, number> = { week: 6, month: 29 };

// Quadrant names reuse the kanban dictionary (one RU name per concept);
// keys are the wire contract, never copy.
const QUADRANT_KEYS: QuadrantKey[] = [
  "important_urgent",
  "important_not_urgent",
  "urgent_not_important",
  "neither",
];
const QUADRANT_LABELS: Record<QuadrantKey, MessageKey> = {
  important_urgent: "kanban.quadrant-both",
  important_not_urgent: "kanban.quadrant-important",
  urgent_not_important: "kanban.quadrant-urgent",
  neither: "kanban.quadrant-plain",
};

function chartLabels(): ChartLabels {
  return {
    blocks: t("stats.blocks"),
    minutes: t("stats.minutes"),
    estimate: t("stats.estimate"),
    actual: t("stats.actual"),
    tasks: t("stats.tasks"),
    doneRatio: t("stats.done-ratio"),
    weekdays: t("stats.weekdays").split(","),
    months: t("stats.months").split(","),
  };
}

export function StatsScreen() {
  const [period, setPeriod] = useState<Period>("month");
  const epoch = useThemeEpoch();
  const from = isoDaysAgo(PERIOD_DAYS[period]);
  const to = isoDaysAgo(0);
  const { data } = useQuery({
    queryKey: ["stats", from, to],
    queryFn: () => api.getStats(from, to),
  });

  const options = useMemo(() => {
    if (!data) return null;
    const theme = chartThemeFrom();
    const labels = chartLabels();
    return {
      heatmap: heatmapOption(data.heatmap, data.period, theme, labels),
      estimate: estimateVsFactOption(data.estimate_vs_fact, theme, labels),
      quadrants: quadrantsOption(
        data.quadrants,
        theme,
        QUADRANT_KEYS.map((key) => t(QUADRANT_LABELS[key]))
      ),
      depth: goalDepthOption(data.goal_depth, theme),
    };
  },
  // epoch is a deliberate recompute trigger (theme repaint), not a read dep.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  [data, epoch]);

  if (!data) {
    return (
      <section className="mx-auto w-full max-w-4xl space-y-4" data-testid="stats.screen">
        <h1 className="text-lg font-bold">{t("stats.title")}</h1>
        <div className="grid gap-4 md:grid-cols-2" data-testid="stats.skeleton">
          <div className="h-40 rounded-card border bg-card/40" />
          <div className="h-40 rounded-card border bg-card/40" />
        </div>
      </section>
    );
  }

  if (data.totals.tasks_total === 0) {
    return (
      <section className="mx-auto w-full max-w-4xl space-y-4" data-testid="stats.screen">
        <h1 className="text-lg font-bold">{t("stats.title")}</h1>
        <p
          className="rounded-card border bg-card px-4 py-8 text-center text-sm text-muted-foreground"
          data-testid="stats.empty"
        >
          {t("stats.empty")}
        </p>
      </section>
    );
  }

  const totals: { id: string; label: MessageKey; value: string }[] = [
    { id: "blocks", label: "summary.blocks", value: String(data.totals.blocks_done) },
    { id: "focus", label: "summary.focus", value: `${data.totals.focus_min} ${t("summary.min")}` },
    {
      id: "score",
      label: "dial.average-score",
      value: data.totals.average_score === null ? "—" : data.totals.average_score.toFixed(1),
    },
    { id: "reviews", label: "dial.reviews-count", value: String(data.totals.reviews_count) },
    { id: "tasks", label: "summary.tasks", value: String(data.totals.tasks_done) },
    { id: "total", label: "stats.tasks-total", value: String(data.totals.tasks_total) },
  ];

  return (
    <section className="mx-auto w-full max-w-4xl space-y-4" data-testid="stats.screen">
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="mr-auto text-lg font-bold">{t("stats.title")}</h1>
        <div className="flex gap-1" role="group" aria-label={t("stats.title")}>
          {(["week", "month"] as const).map((value) => (
            <button
              key={value}
              type="button"
              aria-pressed={period === value}
              data-testid={`stats.period-${value}`}
              onClick={() => setPeriod(value)}
              className={
                period === value
                  ? "rounded-md border bg-primary px-3 py-1 text-sm text-primary-foreground"
                  : "rounded-md border bg-card px-3 py-1 text-sm hover:bg-muted"
              }
            >
              {t(value === "week" ? "stats.period-week" : "stats.period-month")}
            </button>
          ))}
        </div>
      </header>

      <dl className="grid grid-cols-3 gap-3 md:grid-cols-6">
        {totals.map((stat) => (
          <div
            key={stat.id}
            className="rounded-card border bg-card px-3 py-2 text-center"
            data-testid={`stats.stat-${stat.id}`}
          >
            <dd className="text-base font-semibold tabular-nums">{stat.value}</dd>
            <dt className="text-[10px] text-muted-foreground">{t(stat.label)}</dt>
          </div>
        ))}
      </dl>

      <Widget titleKey="stats.widget-streak">
        <div className="flex gap-6 px-4 py-3">
          <StreakValue id="current" label={t("stats.streak-current")} value={data.streak.current} />
          <StreakValue id="record" label={t("stats.streak-record")} value={data.streak.record} />
        </div>
      </Widget>

      {options && (
        <>
          <Widget titleKey="stats.widget-heatmap">
            <Chart option={options.heatmap} testId="stats.widget-heatmap" height={180} />
          </Widget>
          <Widget titleKey="stats.widget-estimate">
            <p className="px-4 pt-2 text-xs text-muted-foreground" data-testid="stats.ratio">
              {t("stats.ratio")}:{" "}
              <strong className="text-sm tabular-nums">
                {data.estimate_vs_fact.ratio ?? "—"}
              </strong>
            </p>
            <Chart option={options.estimate} testId="stats.widget-estimate" height={200} />
          </Widget>
          <div className="grid gap-4 md:grid-cols-2">
            <Widget titleKey="stats.widget-quadrants">
              <Chart option={options.quadrants} testId="stats.widget-quadrants" height={200} />
            </Widget>
            <Widget titleKey="stats.widget-goal-depth">
              <Chart option={options.depth} testId="stats.widget-goal-depth" height={200} />
            </Widget>
          </div>
        </>
      )}

      {data.parents.length > 0 && (
        <Widget titleKey="stats.widget-parents">
          <ul className="space-y-2 px-4 py-3">
            {data.parents.map((row) => (
              <li key={row.task_id} data-testid={`stats.parent-${row.task_id}`} className="text-sm">
                <div className="flex justify-between gap-2">
                  <span className="truncate">{row.title}</span>
                  <span className="tabular-nums text-muted-foreground">
                    {row.done_children}/{row.total_children}
                  </span>
                </div>
                <progress
                  value={row.done_children}
                  max={row.total_children}
                  className="h-1 w-full"
                />
              </li>
            ))}
          </ul>
        </Widget>
      )}

      {data.zombies.count > 0 && (
        <Widget titleKey="stats.widget-zombies">
          <ul className="space-y-1 px-4 py-3">
            {data.zombies.items.map((item) => (
              <li
                key={item.task_id}
                data-testid={`stats.zombie-${item.task_id}`}
                className="flex justify-between gap-2 text-sm"
              >
                <span className="truncate">{item.title}</span>
                <span className="shrink-0 tabular-nums text-warning">
                  {item.days_stuck} {t("stats.zombie-days")}
                </span>
              </li>
            ))}
          </ul>
        </Widget>
      )}
    </section>
  );
}

function Widget({
  titleKey,
  children,
}: {
  titleKey: MessageKey;
  children: React.ReactNode;
}) {
  return (
    <section className="overflow-hidden rounded-card border bg-card shadow-card">
      <h2 className="border-b px-4 py-2 text-xs uppercase tracking-[0.2em] text-muted-foreground">
        {t(titleKey)}
      </h2>
      {children}
    </section>
  );
}

function StreakValue({ id, label, value }: { id: string; label: string; value: number }) {
  return (
    <div className="text-center" data-testid={`stats.streak-${id}`}>
      <div className="text-2xl font-bold tabular-nums">{value}</div>
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
    </div>
  );
}
