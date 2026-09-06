import { useDroppable } from "@dnd-kit/core";
import { Pencil, X } from "lucide-react";
import type { ReactNode } from "react";
import type { BoardColumn } from "../../features/kanban/board";
import { cn } from "../../lib/utils";

const COLUMN_ACCENT: Record<BoardColumn, string> = {
  backlog: "bg-col-backlog",
  planned: "bg-col-planned",
  doing: "bg-col-doing",
  done: "bg-col-done",
};

interface Props {
  column: BoardColumn;
  title: string;
  count: number;
  /** Whether the active card can legally land here (drop-zone highlight). */
  canReceive: boolean;
  editing: boolean;
  onEditToggle: () => void;
  children: ReactNode;
}

export function KanbanColumn({
  column,
  title,
  count,
  canReceive,
  editing,
  onEditToggle,
  children,
}: Props) {
  const { setNodeRef, isOver } = useDroppable({ id: column });
  return (
    <section
      ref={setNodeRef}
      data-testid={`kanban.column-${column}`}
      className={cn(
        "flex min-w-0 flex-col rounded-card border bg-card/60 transition-colors",
        canReceive && "border-dashed",
        isOver && canReceive && "ring-2 ring-ring ring-offset-2 ring-offset-background",
      )}
    >
      <header className="flex items-center gap-2 border-b px-3 py-2">
        <span className={cn("h-2.5 w-2.5 shrink-0 rounded-full", COLUMN_ACCENT[column])} />
        <h2 className="text-sm font-semibold capitalize">{title}</h2>
        <span className="ml-auto text-xs tabular-nums text-muted-foreground">{count}</span>
        <button
          type="button"
          onClick={onEditToggle}
          data-testid={`kanban.edit-toggle-${column}`}
          aria-pressed={editing}
          className={cn(
            "rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
            editing && "bg-muted text-foreground",
          )}
          title={editing ? "Готово" : "Редактировать задачи"}
        >
          {editing ? <X className="h-4 w-4" /> : <Pencil className="h-4 w-4" />}
        </button>
      </header>
      <div className="flex flex-col gap-2 overflow-y-auto p-2">{children}</div>
    </section>
  );
}
