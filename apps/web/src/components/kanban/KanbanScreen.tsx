import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import { Plus } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, ApiError, type TaskDto, type TaskStatus } from "@/api/client";
import { KanbanColumn } from "@/components/kanban/KanbanColumn";
import { TaskCard } from "@/components/kanban/TaskCard";
import { TaskPanel } from "@/components/kanban/TaskPanel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { BOARD_COLUMNS, columnOf, deleteErrorKey, dropTarget, type BoardColumn } from "@/features/kanban/board";
import {
  useCloneTask,
  useCreateTask,
  useDeleteTask,
  useFrogId,
  useMoveTask,
  usePatchTask,
  useTasks,
  TASKS_KEY,
} from "@/features/kanban/hooks";
import { deriveSlots, planIdForDate } from "@/features/kanban/planner";
import { isFrogCard, needsWhenThen } from "@/features/kanban/science";
import { sprintDays } from "@/features/kanban/recurrence";
import { useSprints } from "@/features/sprints/hooks";
import { useUiSettings } from "@/features/settings/hooks";
import { t } from "@/i18n/ru";
import { cn } from "@/lib/utils";

/** today's ISO date in the browser's local zone (the dial plans by local day) */
function today(): string {
  return new Date().toLocaleDateString("en-CA");
}

export function KanbanScreen() {
  const { tasks, byId, error: loadError, isLoading } = useTasks();
  const { data: frog } = useFrogId();
  const { data: settings } = useUiSettings();
  const { active: activeSprint } = useSprints();
  // DF6 (spec 06): the amber nag rings honour the switch; until settings
  // load (or if the server is down) the current behavior (on) holds.
  const wetEnabled = settings?.ui.wet_hints ?? true;
  const client = useQueryClient();
  const move = useMoveTask();
  const patch = usePatchTask();
  const create = useCreateTask();
  const remove = useDeleteTask();
  const clone = useCloneTask();

  const [draggedId, setDraggedId] = useState<string | null>(null);
  const [panelId, setPanelId] = useState<string | null>(null); // DF2 card panel
  const [conflictToast, setConflictToast] = useState<string | null>(null);
  const [newTitle, setNewTitle] = useState("");

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
  );
  const dragged = draggedId ? byId.get(draggedId) : undefined;
  const panelTask = panelId ? byId.get(panelId) ?? null : null;
  // Stable identity: TaskPanel's focus/Esc effect must not re-run while
  // optimistic patches re-render the screen (it would steal input focus).
  const closePanel = useCallback(() => setPanelId(null), []);

  const planTasks = useMemo(() => {
    const doing = tasks.filter((task) => task.status === "doing");
    return deriveSlots(doing);
  }, [tasks]);

  /** DF8: the sprint-day tick row (labels in the board's dd.MM form). */
  const repeatDays = useMemo(
    () =>
      sprintDays(activeSprint).map((iso) => ({
        iso,
        label: `${iso.slice(8)}.${iso.slice(5, 7)}`,
      })),
    [activeSprint],
  );

  /** Re-PUT the derived day plan after any doing-column change. */
  async function syncPlan(): Promise<void> {
    const latest = client.getQueryData<TaskDto[]>(TASKS_KEY) ?? [];
    const slots = deriveSlots(latest.filter((task) => task.status === "doing"));
    const date = today();
    if (slots.length === 0) {
      // V9: an empty plan is not sendable — but it must still be forgotten
      // (DF1): leftover ghost slots would block the cards' deletion.
      await api.clearDayPlan(date).catch(() => undefined);
      return;
    }
    await api.putDayPlan({ id: planIdForDate(date), date, slots });
  }

  function onDragStart(event: DragStartEvent) {
    setDraggedId(String(event.active.id));
  }

  async function onDragEnd(event: DragEndEvent) {
    setDraggedId(null);
    const { active, over } = event;
    if (!over) return;
    const task = byId.get(String(active.id));
    const to = String(over.id) as TaskStatus;
    if (!task || dropTarget(task.status, to) === null) return;
    try {
      await move.mutateAsync({ id: task.id, to });
    } catch (error) {
      // optimistic cache already rolled back in onError; announce the
      // server's own reason (illegal transition vs in-work capacity)
      setConflictToast(
        error instanceof ApiError && error.message
          ? error.message
          : t("kanban.conflict-moved-back"),
      );
      window.setTimeout(() => setConflictToast(null), 3500);
      return;
    }
    void syncPlan();
  }

  async function onFieldChange(id: string, changes: Partial<TaskDto>) {
    await patch.mutateAsync({ id, changes }).catch(() => undefined);
    void syncPlan();
  }

  /** DF1: a refused delete explains itself in RU instead of vanishing silently. */
  async function onDelete(id: string) {
    try {
      await remove.mutateAsync(id);
    } catch (error) {
      const message = error instanceof ApiError ? deleteErrorKey(error.message) : "kanban.delete-failed";
      setConflictToast(t(message));
      window.setTimeout(() => setConflictToast(null), 5000);
    }
  }

  async function onCreate() {
    const title = newTitle.trim();
    if (!title) return;
    await create
      .mutateAsync({
        id: `task-${crypto.randomUUID().slice(0, 12)}`,
        title,
        type: "normal",
        important: false,
        urgent: false,
        estimate_blocks: 1,
      })
      .catch(() => undefined);
    setNewTitle("");
  }

  const columnTitles: Record<BoardColumn, string> = {
    backlog: t("kanban.column-backlog"),
    planned: t("kanban.column-planned"),
    doing: t("kanban.column-doing"),
    done: t("kanban.column-done"),
  };

  return (
    <div className="flex flex-col gap-4" data-testid="kanban.screen">
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void onCreate();
        }}
      >
        <Input
          data-testid="kanban.create-input"
          placeholder={t("kanban.create-placeholder")}
          value={newTitle}
          onChange={(e) => setNewTitle(e.target.value)}
        />
        <Button type="submit" data-testid="kanban.create-submit" disabled={!newTitle.trim()}>
          <Plus className="h-4 w-4" />
          {t("kanban.create-submit")}
        </Button>
      </form>

      {isLoading && <p className="text-sm text-muted-foreground">…</p>}
      {loadError && <p className="text-sm text-danger">{t("error.network")}</p>}

      <DndContext sensors={sensors} onDragStart={onDragStart} onDragEnd={onDragEnd} onDragCancel={() => setDraggedId(null)}>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {BOARD_COLUMNS.map((column) => {
            const cards = columnOf(tasks, column);
            return (
              <KanbanColumn
                key={column}
                column={column}
                title={columnTitles[column]}
                count={cards.length}
                canReceive={Boolean(
                  dragged && dropTarget(dragged.status, column as TaskStatus) !== null,
                )}
              >
                {cards.map((task) => (
                  <TaskCard
                    key={task.id}
                    task={task}
                    wetHint={wetEnabled && needsWhenThen(task)}
                    isFrog={isFrogCard(task.id, frog?.task_id)}
                    onOpen={setPanelId}
                  />
                ))}
              </KanbanColumn>
            );
          })}
        </div>
        <DragOverlay>
          {dragged && (
            <div className={cn("rounded-lg border bg-card px-3 py-2 text-sm shadow-card-drag")}>
              {dragged.title}
            </div>
          )}
        </DragOverlay>
      </DndContext>

      <section className="rounded-card border bg-card p-3" data-testid="kanban.planner">
        <h2 className="text-sm font-semibold">{t("kanban.planner-title")}</h2>
        {planTasks.length === 0 ? (
          <p className="mt-1 text-xs text-muted-foreground">{t("kanban.planner-empty")}</p>
        ) : (
          <ol className="mt-2 flex flex-wrap gap-1.5">
            {planTasks.map((slot) => (
              <li
                key={slot.sector}
                data-testid={`planner.slot-${slot.sector}`}
                className="rounded-md border bg-muted/60 px-2 py-1 text-xs"
              >
                <span className="mr-1 font-mono text-muted-foreground">{slot.sector}</span>
                {byId.get(slot.task_id)?.title ?? "—"}
              </li>
            ))}
          </ol>
        )}
      </section>

      {conflictToast && (
        <div
          role="status"
          data-testid="kanban.conflict-toast"
          className="fixed bottom-6 left-1/2 -translate-x-1/2 rounded-lg bg-foreground px-4 py-2 text-sm text-background shadow-card-drag"
        >
          {conflictToast}
        </div>
      )}

      {panelTask && (
        <TaskPanel
          task={panelTask}
          parents={tasks}
          sprintDays={repeatDays}
          onChange={onFieldChange}
          onDelete={(id) => void onDelete(id)}
          onClone={(id) =>
            void clone
              .mutateAsync({ id, cloneId: `task-${crypto.randomUUID().slice(0, 12)}` })
              .catch(() => undefined)
          }
          onClose={closePanel}
        />
      )}
    </div>
  );
}
