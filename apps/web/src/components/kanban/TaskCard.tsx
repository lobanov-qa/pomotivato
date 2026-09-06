import { useDraggable } from "@dnd-kit/core";
import { CSS } from "@dnd-kit/utilities";
import { ChevronDown, GripVertical, Trash2 } from "lucide-react";
import { useState } from "react";
import type { TaskDto, TaskStatus, TaskType } from "@/api/client";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n/ru";
import { cn } from "@/lib/utils";
import {
  QUADRANT_KEY,
  QUADRANT_VALUE,
  quadrantOf,
  TYPE_KEY,
  type Quadrant,
} from "./taskMeta";

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
  /** Column edit mode: every card becomes an editable form (spec §2: kanban
   * is the ONLY screen that edits tasks). */
  editing: boolean;
  onChange: (id: string, changes: Partial<TaskDto>) => void;
  onDelete: (id: string) => void;
  /** Other tasks for the parent selector (only top-level, non-self). */
  parents: TaskDto[];
}

export function TaskCard({ task, editing, onChange, onDelete, parents }: Props) {
  const [scienceOpen, setScienceOpen] = useState(false);
  const drag = useDraggable({ id: task.id, disabled: editing });
  const listeners = drag.listeners ?? {};
  const style = { transform: CSS.Translate.toString(drag.transform) };

  const setRefs = (node: HTMLElement | null) => {
    // dnd-kit needs the node's layout rect to compute drop targets;
    // without it `over` is always null and drops silently no-op.
    drag.setNodeRef(node);
  };

  const set = (changes: Partial<TaskDto>) => onChange(task.id, changes);

  return (
    <article
      ref={setRefs}
      data-testid={`task-card.root-${task.id}`}
      style={style}
      className={cn(
        "group relative rounded-lg border bg-card p-3 pl-4 shadow-card transition-shadow",
        "before:absolute before:inset-y-1 before:left-1 before:w-1 before:rounded-full before:content-['']",
        STRIPE[task.status],
        "hover:shadow-card-hover",
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
            editing && "pointer-events-none invisible",
          )}
          {...listeners}
          {...(drag.attributes ?? {})}
        >
          <GripVertical className="h-4 w-4" />
        </button>
        {editing ? (
          <input
            data-testid={`task-card.title-${task.id}`}
            className="w-full rounded-md border border-input bg-background px-2 py-1 text-sm font-medium"
            value={task.title}
            onChange={(e) => set({ title: e.target.value })}
          />
        ) : (
          <h3
            className={cn(
              "min-w-0 flex-1 text-sm font-medium leading-5",
              task.status === "done" && "line-through",
            )}
          >
            {task.title}
          </h3>
        )}
      </div>

      {editing ? (
        <div className="mt-2 flex flex-col gap-2">
          <div className="grid grid-cols-2 gap-2">
            <label className="flex flex-col gap-1">
              <span className="text-xs text-muted-foreground">{t("kanban.field-type")}</span>
              <select
                data-testid={`task-card.type-${task.id}`}
                className="h-8 rounded-md border border-input bg-background px-2 text-sm"
                value={task.type}
                onChange={(e) => set({ type: e.target.value as TaskType })}
              >
                {(Object.keys(TYPE_KEY) as TaskType[]).map((value) => (
                  <option key={value} value={value}>
                    {t(TYPE_KEY[value])}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-muted-foreground">{t("kanban.field-quadrant")}</span>
              <select
                data-testid={`task-card.quadrant-${task.id}`}
                className="h-8 rounded-md border border-input bg-background px-2 text-sm"
                value={quadrantOf(task)}
                onChange={(e) =>
                  set(QUADRANT_VALUE[e.target.value as Quadrant] as Partial<TaskDto>)
                }
              >
                {(Object.keys(QUADRANT_KEY) as Quadrant[]).map((value) => (
                  <option key={value} value={value}>
                    {t(QUADRANT_KEY[value])}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-muted-foreground">{t("kanban.field-blocks")}</span>
              <input
                type="number"
                min={1}
                max={12}
                data-testid={`task-card.blocks-${task.id}`}
                className="h-8 rounded-md border border-input bg-background px-2 text-sm"
                value={task.estimate_blocks}
                onChange={(e) =>
                  set({ estimate_blocks: Math.max(1, Number(e.target.value) || 1) })
                }
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-muted-foreground">{t("kanban.field-parent")}</span>
              <select
                data-testid={`task-card.parent-${task.id}`}
                className="h-8 rounded-md border border-input bg-background px-2 text-sm"
                value={task.parent_id ?? ""}
                onChange={(e) => set({ parent_id: e.target.value || null })}
              >
                <option value="">{t("kanban.parent-none")}</option>
                {parents
                  .filter((p) => p.id !== task.id && !p.parent_id)
                  .map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.title}
                    </option>
                  ))}
              </select>
            </label>
          </div>

          <button
            type="button"
            data-testid={`task-card.science-toggle-${task.id}`}
            onClick={() => setScienceOpen((v) => !v)}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            <ChevronDown className={cn("h-3 w-3 transition-transform", scienceOpen && "rotate-180")} />
            {t("kanban.science-toggle")}
          </button>
          {scienceOpen && (
            <div className="flex flex-col gap-2 rounded-md bg-muted/50 p-2">
              <label className="flex flex-col gap-1">
                <span className="text-xs text-muted-foreground">
                  {t("kanban.field-deadline")}
                </span>
                <input
                  type="date"
                  data-testid={`task-card.deadline-${task.id}`}
                  className="h-8 rounded-md border border-input bg-background px-2 text-sm"
                  value={task.deadline ?? ""}
                  onChange={(e) => set({ deadline: e.target.value || null })}
                />
              </label>
              {(
                [
                  ["when_then", "kanban.field-when-then"],
                  ["done_criteria", "kanban.field-done-criteria"],
                  ["benefit", "kanban.field-benefit"],
                ] as const
              ).map(([field, labelKey]) => (
                <input
                  key={field}
                  data-testid={`task-card.${field}-${task.id}`}
                  placeholder={t(labelKey)}
                  className="h-8 rounded-md border border-input bg-background px-2 text-sm"
                  value={task[field] ?? ""}
                  onChange={(e) => set({ [field]: e.target.value || null })}
                />
              ))}
            </div>
          )}

          {task.status === "backlog" && (
            <Button
              variant="danger"
              size="sm"
              data-testid={`task-card.delete-${task.id}`}
              onClick={() => onDelete(task.id)}
              className="self-start"
            >
              <Trash2 className="h-3.5 w-3.5" />
              {t("kanban.delete")}
            </Button>
          )}
        </div>
      ) : (
        <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-0.5 pl-6 text-xs text-muted-foreground">
          <span data-testid={`task-card.type-${task.id}`}>{t(TYPE_KEY[task.type])}</span>
          <span aria-hidden>·</span>
          <span data-testid={`task-card.quadrant-${task.id}`}>{t(QUADRANT_KEY[quadrantOf(task)])}</span>
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
      )}
    </article>
  );
}
