import { useDraggable } from "@dnd-kit/core";
import { CSS } from "@dnd-kit/utilities";
import { GripVertical, Pencil } from "lucide-react";
import type { TaskDto, TaskStatus } from "@/api/client";
import { t } from "@/i18n/ru";
import { cn } from "@/lib/utils";
import { QUADRANT_KEY, quadrantOf, TYPE_KEY } from "./taskMeta";

/** Left color stripe by status (the board reads at a glance). */
const STRIPE: Record<TaskStatus, string> = {
  backlog: "before:bg-col-backlog",
  planned: "before:bg-col-planned",
  doing: "before:bg-col-doing",
  done: "before:bg-col-done",
  archived: "before:bg-muted-foreground",
};

interface Props {
  task: TaskDto;
  /** DF2 (spec 06): opens the side edit panel for this card. */
  onOpen: (id: string) => void;
  /** V8-soft ring: scheduled card with a blank when_then (spec 05 §3.1). */
  wetHint: boolean;
  /** The card is the server's frog candidate (spec 05 §3.9): badge only. */
  isFrog: boolean;
}

export function TaskCard({ task, onOpen, wetHint, isFrog }: Props) {
  const drag = useDraggable({ id: task.id });
  const listeners = drag.listeners ?? {};
  const style = { transform: CSS.Translate.toString(drag.transform) };

  const setRefs = (node: HTMLElement | null) => {
    // dnd-kit needs the node's layout rect to compute drop targets;
    // without it `over` is always null and drops silently no-op.
    drag.setNodeRef(node);
  };

  return (
    <article
      ref={setRefs}
      data-testid={`task-card.root-${task.id}`}
      style={style}
      className={cn(
        "group relative rounded-lg border bg-card p-3 pl-4 shadow-card transition-shadow",
        "before:absolute before:inset-y-1 before:left-1 before:w-1 before:rounded-full before:content['']",
        STRIPE[task.status],
        "hover:shadow-card-hover",
        wetHint && "ring-2 ring-warning/60",
        drag.isDragging && "z-10 opacity-90 shadow-card-drag",
        task.status === "done" && "opacity-70",
      )}
    >
      <div className="flex items-start gap-2">
        <button
          type="button"
          data-testid={`task-card.grip-${task.id}`}
          aria-label={t("kanban.card-grip")}
          className={cn(
            "-ml-1 mt-0.5 shrink-0 cursor-grab touch-none rounded p-0.5 text-muted-foreground",
            "opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100",
          )}
          {...listeners}
          {...(drag.attributes ?? {})}
        >
          <GripVertical className="h-4 w-4" />
        </button>
        <button
          type="button"
          data-testid={`task-card.open-${task.id}`}
          onClick={() => onOpen(task.id)}
          className="min-w-0 flex-1 text-left"
        >
          <h3
            className={cn(
              "min-w-0 text-sm font-medium leading-5",
              task.status === "done" && "line-through",
            )}
          >
            {task.title}
          </h3>
        </button>
        <button
          type="button"
          data-testid={`task-card.edit-${task.id}`}
          aria-label={t("kanban.card-edit")}
          onClick={() => onOpen(task.id)}
          className={cn(
            "shrink-0 rounded p-0.5 text-muted-foreground opacity-0 transition-opacity",
            "group-hover:opacity-100 focus-visible:opacity-100 hover:bg-muted hover:text-foreground",
          )}
        >
          <Pencil className="h-3.5 w-3.5" />
        </button>
        {isFrog && (
          <span
            data-testid={`task-card.frog-badge-${task.id}`}
            title={t("kanban.frog-title")}
            className="shrink-0 rounded-full bg-warning/15 px-1.5 text-sm leading-5"
            aria-label={t("kanban.frog-title")}
          >
            🐸
          </span>
        )}
      </div>
      {wetHint && (
        <p data-testid={`task-card.wt-hint-${task.id}`} className="mt-1 text-xs text-warning">
          {t("kanban.wt-hint")}
        </p>
      )}
      <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-0.5 pl-6 text-xs text-muted-foreground">
        {task.no_timer && (
          <span data-testid={`task-card.no-timer-${task.id}`} className="rounded bg-muted px-1">
            {t("kanban.no-timer-badge")}
          </span>
        )}
        <span data-testid={`task-card.type-${task.id}`}>{t(TYPE_KEY[task.type])}</span>
        <span aria-hidden>·</span>
        <span data-testid={`task-card.quadrant-${task.id}`}>
          {t(QUADRANT_KEY[quadrantOf(task)])}
        </span>
        {task.estimate_blocks !== 1 && (
          <>
            <span aria-hidden>·</span>
            <span data-testid={`task-card.blocks-${task.id}`}>
              {task.estimate_blocks} × {t("kanban.planner-sector").toLowerCase()}
            </span>
          </>
        )}
        {task.deadline && (
          <>
            <span aria-hidden>·</span>
            <span className="text-warning" data-testid={`task-card.deadline-${task.id}`}>
              {task.deadline}
            </span>
          </>
        )}
      </div>
    </article>
  );
}
