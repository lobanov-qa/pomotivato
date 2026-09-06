/**
 * Day summary panel (spec 03 §5): numbers from GET /api/summary/{date} —
 * the server's read-side projection, the client adds no arithmetic.
 */

import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { t } from "@/i18n/ru";

function today(): string {
  return new Date().toLocaleDateString("en-CA");
}

export function SummaryPanel() {
  const date = today();
  const { data } = useQuery({
    queryKey: ["summary", date],
    queryFn: () => api.getSummary(date),
    refetchInterval: 30_000, // the day accumulates while the app is open
  });

  if (!data) return null;

  const stats: { id: string; label: string; value: string }[] = [
    { id: "blocks", label: t("summary.blocks"), value: `${data.blocks_done} / ${data.blocks_planned}` },
    { id: "focus", label: t("summary.focus"), value: `${data.focus_min} ${t("summary.min")}` },
    {
      id: "score",
      label: t("dial.average-score"),
      value: data.average_score === null ? "—" : data.average_score.toFixed(1),
    },
    { id: "tasks", label: t("summary.tasks"), value: String(data.tasks_done) },
  ];

  return (
    <section
      className="flex w-full max-w-md items-center justify-between gap-4 rounded-card border bg-card px-4 py-3"
      data-testid="summary.panel"
    >
      <h2 className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
        {t("summary.title")}
      </h2>
      <dl className="flex gap-5">
        {stats.map((stat) => (
          <div
            key={stat.id}
            className="text-center"
            data-testid={`summary.stat-${stat.id}`}
          >
            <dd className="text-sm font-semibold tabular-nums">{stat.value}</dd>
            <dt className="text-[10px] text-muted-foreground">{stat.label}</dt>
          </div>
        ))}
      </dl>
    </section>
  );
}
