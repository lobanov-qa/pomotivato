/**
 * «Задачи спринта» block of the sprint card (spec 07 §4.1.4, E4c PR 7).
 * The card lists its own tasks (status + day circles); on a completed
 * sprint the block grows the fate menu per undecided card (A40) and the
 * bulk «Оставить все как есть». Clicking a task jumps to /tasks scoped to
 * the sprint with the side panel open (the panel lives on the board — one
 * owner of card editing, §4.8: the click "opens the panel as usual").
 */

import { Link } from "react-router-dom";
import type { SprintDto, TaskDto } from "@/api/client";
import { TICK_CLASS, tickStates } from "@/features/kanban/tickStates";
import { useCarryChoice, useCarryChoiceAll } from "@/features/sprints/hooks";
import { type MessageKey, t } from "@/i18n/ru";
import { cn } from "@/lib/utils";
import { todayIso } from "@/features/week/dates";

interface Props {
  sprint: SprintDto;
  tasks: TaskDto[];
  /** Active sprints the fate menu may copy into (V28/A13 server-side too). */
  activeSprints: SprintDto[];
}

const COLUMN_KEYS: Record<TaskDto["status"], MessageKey> = {
  backlog: "kanban.column-backlog",
  planned: "kanban.column-planned",
  doing: "kanban.column-doing",
  done: "kanban.column-done",
  archived: "kanban.column-archived",
};

export function SprintTasksBlock({ sprint, tasks, activeSprints }: Props) {
  const carry = useCarryChoice();
  const carryAll = useCarryChoiceAll();
  const decided = sprint.status === "completed" && sprint.carry_pending > 0;
  const today = todayIso();

  if (tasks.length === 0) {
    return (
      <p className="text-xs text-muted-foreground" data-testid="sprint.tasks-empty">
        {sprint.status === "planned" ? t("sprint.tasks-empty-planned") : t("sprint.tasks-none")}
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-1" data-testid="sprint.tasks">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {t("sprint.tasks-title")}
        </h3>
        {decided && (
          <button
            type="button"
            data-testid="sprint.fate-leave-all"
            disabled={carryAll.isPending}
            onClick={() => carryAll.mutate(sprint.id)}
            className="rounded-md border px-2 py-0.5 text-xs hover:bg-muted"
          >
            {t("sprint.fate-leave-all")}
          </button>
        )}
      </div>
      {tasks.map((task) => (
        <div
          key={task.id}
          data-testid={`sprint.task-${task.id}`}
          className="flex flex-wrap items-center gap-2 rounded-md border bg-background px-2 py-1 text-sm"
        >
          <Link
            to={`/tasks?sprint=${sprint.id}&task=${task.id}`}
            className="flex-1 truncate hover:underline"
            data-testid={`sprint.task-open-${task.id}`}
          >
            {task.title}
          </Link>
          <span className="text-xs text-muted-foreground">{t(COLUMN_KEYS[task.status])}</span>
          <DayCircles task={task} today={today} />
          {sprint.status === "completed" && task.carry_choice === null && (
            <FateMenu
              task={task}
              activeSprints={activeSprints}
              pending={carry.isPending}
              onChoose={(body) => carry.mutate({ taskId: task.id, body })}
            />
          )}
          {sprint.status === "completed" && task.carry_choice !== null && (
            <span className="text-xs text-muted-foreground" data-testid={`sprint.task-fate-${task.id}`}>
              {task.carry_choice === "left" ? t("sprint.fate-leave") : t("sprint.fate-move", "ru", { name: "" })}
            </span>
          )}
        </div>
      ))}
      {carry.error && <p className="text-xs text-danger">{carry.error.message}</p>}
    </div>
  );
}

/** Progress circles of the card's ticks (worked / missed / planned, §4.5). */
export function DayCircles({ task, today }: { task: TaskDto; today: string }) {
  const ticks = tickStates(task, today);
  if (ticks.length === 0) return null;
  return (
    <span className="flex gap-0.5" data-testid={`sprint.task-days-${task.id}`}>
      {ticks.map(({ iso, state }) => (
        <span
          key={iso}
          title={iso}
          className={cn("h-2.5 w-2.5 rounded-full border", TICK_CLASS[state])}
        />
      ))}
    </span>
  );
}

function FateMenu({
  task,
  activeSprints,
  pending,
  onChoose,
}: {
  task: TaskDto;
  activeSprints: SprintDto[];
  pending: boolean;
  onChoose: (body: { target_sprint_id?: string | null; leave?: boolean }) => void;
}) {
  const noTargets = activeSprints.length === 0;
  return (
    <select
      data-testid={`sprint.fate-${task.id}`}
      disabled={pending}
      defaultValue=""
      title={noTargets ? t("sprint.fate-hint") : undefined}
      onChange={(event) => {
        const value = event.target.value;
        if (value === "") return;
        if (value === "leave") onChoose({ leave: true });
        else if (value === "shelf") onChoose({ target_sprint_id: null });
        else onChoose({ target_sprint_id: value });
      }}
      className="rounded-md border bg-background px-1 text-xs"
    >
      <option value="" disabled>
        {t("sprint.fate-badge")}
      </option>
      {activeSprints.map((sp) => (
        <option key={sp.id} value={sp.id}>
          {t("sprint.fate-move", "ru", { name: `${sp.number}${sp.name ? ` — ${sp.name}` : ""}` })}
        </option>
      ))}
      <option value="shelf">{t("sprint.fate-shelf")}</option>
      <option value="leave">{t("sprint.fate-leave")}</option>
    </select>
  );
}
