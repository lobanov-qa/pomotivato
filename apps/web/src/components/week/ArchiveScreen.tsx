/**
 * Archive page (spec 07 §4.8, A38, E4c PR 7): read-only inventory of all
 * sprints newest-number-first with their task lists — title, status,
 * deadline and the day circles in the usual coloring. No editing here: a
 * task click jumps to the board scoped to its sprint with the side panel
 * open (the panel is the one card editor). Shelf tasks stay out of the
 * page entirely (A24). Deleting lives in the sprint card, not here.
 */

import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type SprintDto } from "@/api/client";
import { DayCircles } from "@/components/week/SprintTasksBlock";
import { useSprints } from "@/features/sprints/hooks";
import { todayIso } from "@/features/week/dates";
import { t } from "@/i18n/ru";

const COLUMN_KEYS: Record<string, "kanban.column-backlog" | "kanban.column-planned" | "kanban.column-doing" | "kanban.column-done" | "kanban.column-archived"> = {
  backlog: "kanban.column-backlog",
  planned: "kanban.column-planned",
  doing: "kanban.column-doing",
  done: "kanban.column-done",
  archived: "kanban.column-archived",
};

export function ArchiveScreen() {
  const { sprints } = useSprints();
  const ordered = [...sprints].sort((a, b) => b.number - a.number);
  return (
    <section className="flex flex-col gap-4" data-testid="archive.screen">
      <header>
        <h1 className="text-lg font-semibold">{t("archive.title")}</h1>
        <p className="text-xs text-muted-foreground">{t("archive.subtitle")}</p>
      </header>
      {ordered.length === 0 && (
        <p className="text-sm text-muted-foreground" data-testid="archive.empty">
          {t("archive.empty")}
        </p>
      )}
      {ordered.map((sprint) => (
        <SprintSection key={sprint.id} sprint={sprint} />
      ))}
      <p className="text-xs text-muted-foreground" data-testid="archive.shelf-note">
        {t("archive.shelf-note")}
      </p>
    </section>
  );
}

function SprintSection({ sprint }: { sprint: SprintDto }) {
  // Per-sprint detail is the list-with-archived endpoint (§4.8: existing
  // endpoints are enough); queries are cached by sprint id.
  const detail = useQuery({
    queryKey: ["sprints", sprint.id],
    queryFn: () => api.getSprintDetail(sprint.id),
  });
  const today = todayIso();
  return (
    <div className="flex flex-col gap-1" data-testid={`archive.sprint-${sprint.id}`}>
      <h2 className="text-sm font-semibold">
        {`${t("sprint.title")} ${sprint.number}${sprint.name ? ` — ${sprint.name}` : ""}`}
        <span className="ml-2 text-xs tabular-nums text-muted-foreground">
          {sprint.start_date} → {sprint.end_date}
        </span>
      </h2>
      {(detail.data?.tasks.length ?? 0) === 0 && (
        <p className="text-xs text-muted-foreground">{t("sprint.tasks-none")}</p>
      )}
      {(detail.data?.tasks ?? []).map((task) => (
        <div
          key={task.id}
          data-testid={`archive.task-${task.id}`}
          className="flex flex-wrap items-center gap-2 rounded-md border bg-card px-2 py-1 text-sm"
        >
          <Link to={`/tasks?sprint=${sprint.id}&task=${task.id}`} className="flex-1 truncate hover:underline">
            {task.title}
          </Link>
          <span className="text-xs text-muted-foreground">{t(COLUMN_KEYS[task.status])}</span>
          {task.deadline && <span className="text-xs tabular-nums text-muted-foreground">{task.deadline}</span>}
          <DayCircles task={task} today={today} />
        </div>
      ))}
    </div>
  );
}
