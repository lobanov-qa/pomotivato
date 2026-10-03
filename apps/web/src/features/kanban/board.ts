/**
 * Pure kanban board state (no React, no fetch) so the optimistic-move and
 * rollback rules — the tricky part of drag-n-drop — are unit-testable
 * without the DOM. The screen wires these to TanStack Query mutations.
 */

import type { TaskDto, TaskStatus } from "@/api/client";
import type { MessageKey } from "@/i18n/ru";

/** The four playable columns (archived has no lane; delete returns to backlog). */
export const BOARD_COLUMNS = ["backlog", "planned", "doing", "done"] as const;
export type BoardColumn = (typeof BOARD_COLUMNS)[number];

/**
 * V7 mirror for the DRAG affordance only (spec core/validation): which
 * columns a card may be dropped into. The server is still the authority —
 * an illegal drop the UI allowed is rolled back by the 409 handler.
 */
const DRAG_ALLOWED: Record<TaskStatus, readonly TaskStatus[]> = {
  backlog: ["planned"],
  planned: ["doing", "backlog"],
  doing: ["done", "planned"],
  done: ["doing"],
  archived: ["backlog"],
};

export function canDrop(from: TaskStatus, to: TaskStatus): boolean {
  return DRAG_ALLOWED[from].includes(to);
}

/** Move a task to a new status immutably, keeping array order stable. */
export function applyMove(tasks: TaskDto[], id: string, to: TaskStatus): TaskDto[] {
  return tasks.map((task) => (task.id === id ? { ...task, status: to } : task));
}

/** Cards for one column, in server order (created_at,asc — list order). */
export function columnOf(tasks: TaskDto[], column: BoardColumn): TaskDto[] {
  return tasks.filter((task) => task.status === column);
}

/**
 * DF1 (spec 06): a rejected delete must say why in the user's language.
 * Maps the server message to a dictionary key; the EN server text stays
 * the source of truth, this is presentation-only routing.
 */
export function deleteErrorKey(message: string): MessageKey {
  if (message.includes("still has children")) return "kanban.delete-blocked-children";
  if (message.includes("is planned on")) return "kanban.delete-blocked-planned";
  if (message.includes("only backlog/archived")) return "kanban.delete-blocked-status";
  return "kanban.delete-failed";
}

/**
 * The one transition dnd will attempt for a drag from->to, or null when the
 * drop target is illegal / same column (no request should fire). Central so
 * both the highlight (valid vs invalid drop zone) and the commit agree.
 */
export function dropTarget(from: TaskStatus, to: TaskStatus): TaskStatus | null {
  if (from === to) return null;
  return canDrop(from, to) ? to : null;
}
