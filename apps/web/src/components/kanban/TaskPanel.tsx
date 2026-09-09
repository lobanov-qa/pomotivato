/**
 * Task edit panel (spec 06 DF2): a side overlay for ONE card — the Jira
 * drawer pattern. It replaces the column-wide edit mode (author 08.09:
 * editing a whole column at once made cards unwieldy). Overlay rules from
 * U2: Esc and outside-click close it, the dialog is labelled, and focus
 * starts inside. The form fields keep the task-card.* testids (stable
 * licators stay locale-agnostic and the E3 testids survive the move).
 */

import { Copy, Trash2, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { TaskDto, TaskType } from "@/api/client";
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

interface Props {
  task: TaskDto;
  parents: TaskDto[];
  onChange: (id: string, changes: Partial<TaskDto>) => void;
  onDelete: (id: string) => void;
  onClone: (id: string) => void;
  onClose: () => void;
}

export function TaskPanel({ task, parents, onChange, onDelete, onClone, onClose }: Props) {
  const [scienceOpen, setScienceOpen] = useState(true);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onKey(event: KeyboardEvent): void {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    panelRef.current?.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const set = (changes: Partial<TaskDto>) => onChange(task.id, changes);

  return (
    <div
      className="fixed inset-0 z-40 bg-black/30"
      data-testid="task-panel.overlay"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={task.title}
        tabIndex={-1}
        data-testid={`task-panel.root-${task.id}`}
        className="absolute inset-y-0 right-0 flex w-[min(440px,95vw)] flex-col gap-3 overflow-y-auto border-l bg-card p-5 shadow-card-drag outline-none"
      >
        <div className="flex items-center gap-2">
          <h2 className="mr-auto text-sm font-semibold">{t("kanban.panel-title")}</h2>
          <button
            type="button"
            data-testid="task-panel.close"
            aria-label={t("kanban.panel-close")}
            onClick={onClose}
            className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <label className="flex flex-col gap-1">
          <span className="text-xs text-muted-foreground">{t("kanban.field-title")}</span>
          <input
            data-testid={`task-panel.title-${task.id}`}
            className="h-9 w-full rounded-md border border-input bg-background px-2 py-1 text-sm font-medium"
            value={task.title}
            onChange={(e) => set({ title: e.target.value })}
          />
        </label>

        <div className="grid grid-cols-2 gap-2">
          <label className="flex flex-col gap-1">
            <span className="text-xs text-muted-foreground">{t("kanban.field-type")}</span>
            <select
              data-testid={`task-panel.type-${task.id}`}
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
              data-testid={`task-panel.quadrant-${task.id}`}
              className="h-8 rounded-md border border-input bg-background px-2 text-sm"
              value={quadrantOf(task)}
              onChange={(e) => set(QUADRANT_VALUE[e.target.value as Quadrant] as Partial<TaskDto>)}
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
              data-testid={`task-panel.blocks-${task.id}`}
              className="h-8 rounded-md border border-input bg-background px-2 text-sm"
              value={task.estimate_blocks}
              onChange={(e) => set({ estimate_blocks: Math.max(1, Number(e.target.value) || 1) })}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-muted-foreground">{t("kanban.field-parent")}</span>
            <select
              data-testid={`task-panel.parent-${task.id}`}
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
          data-testid={`task-panel.science-toggle-${task.id}`}
          onClick={() => setScienceOpen((v) => !v)}
          className="self-start text-xs text-muted-foreground hover:text-foreground"
        >
          {t("kanban.science-toggle")}
        </button>
        <div className={cn("flex-col gap-2 rounded-md bg-muted/50 p-2", !scienceOpen && "hidden")}>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-muted-foreground">{t("kanban.field-deadline")}</span>
            <input
              type="date"
              data-testid={`task-panel.deadline-${task.id}`}
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
              data-testid={`task-panel.${field}-${task.id}`}
              placeholder={t(labelKey)}
              className="h-8 rounded-md border border-input bg-background px-2 text-sm"
              value={task[field] ?? ""}
              onChange={(e) => set({ [field]: e.target.value || null })}
            />
          ))}
        </div>

        <div className="mt-auto flex gap-2 border-t pt-3">
          {task.status === "backlog" && (
            <Button
              variant="danger"
              size="sm"
              data-testid={`task-panel.delete-${task.id}`}
              onClick={() => onDelete(task.id)}
            >
              <Trash2 className="h-3.5 w-3.5" />
              {t("kanban.delete")}
            </Button>
          )}
          {task.status === "done" && (
            <Button
              variant="ghost"
              size="sm"
              data-testid={`task-panel.clone-${task.id}`}
              onClick={() => onClone(task.id)}
            >
              <Copy className="h-3.5 w-3.5" />
              {t("kanban.clone")}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
