/**
 * Task meta maps shared between card views (kept out of TaskCard.tsx:
 * fast-refresh wants component-only modules, and board tests import these).
 */

import type { TaskDto, TaskType } from "@/api/client";
import { type MessageKey } from "@/i18n/ru";

/** Quadrant = the important x urgent pair, one control (V2 via E1 enums). */
export type Quadrant = "plain" | "important" | "urgent" | "both";

export function quadrantOf(task: Pick<TaskDto, "important" | "urgent">): Quadrant {
  if (task.important && task.urgent) return "both";
  if (task.important) return "important";
  if (task.urgent) return "urgent";
  return "plain";
}

export const QUADRANT_KEY: Record<Quadrant, MessageKey> = {
  plain: "kanban.quadrant-plain",
  important: "kanban.quadrant-important",
  urgent: "kanban.quadrant-urgent",
  both: "kanban.quadrant-both",
};

export const QUADRANT_VALUE: Record<Quadrant, { important: boolean; urgent: boolean }> = {
  plain: { important: false, urgent: false },
  important: { important: true, urgent: false },
  urgent: { important: false, urgent: true },
  both: { important: true, urgent: true },
};

export const TYPE_KEY: Record<TaskType, MessageKey> = {
  normal: "kanban.task-type-normal",
  study: "kanban.task-type-study",
  habit: "kanban.task-type-habit",
};
