/**
 * Tasks query + optimistic status move (spec 03 §2): drag commits
 * POST /tasks/{id}/status instantly in the cache; on 409 (V7) the cache
 * rolls back and the card "flies back" — plus a toast-ready error state.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useRef } from "react";
import { api, type TaskDto, type TaskStatus } from "@/api/client";
import { applyMove } from "@/features/kanban/board";

export const TASKS_KEY = ["tasks"] as const;

export function useTasks() {
  const query = useQuery({
    queryKey: TASKS_KEY,
    queryFn: () => api.listTasks(),
  });
  const tasks = useMemo(() => query.data ?? [], [query.data]);
  const byId = useMemo(() => new Map(tasks.map((t) => [t.id, t])), [tasks]);
  return { ...query, tasks, byId };
}

/** Status move with optimistic cache patch + rollback snapshot. */
export function useMoveTask() {
  const client = useQueryClient();
  const snapshot = useRef<TaskDto[] | null>(null);

  return useMutation({
    mutationFn: ({ id, to }: { id: string; to: TaskStatus }) => api.setTaskStatus(id, to),
    onMutate: async ({ id, to }) => {
      await client.cancelQueries({ queryKey: TASKS_KEY });
      snapshot.current = client.getQueryData<TaskDto[]>(TASKS_KEY) ?? null;
      client.setQueryData<TaskDto[]>(
        TASKS_KEY,
        (old) => (old ? applyMove(old, id, to) : old),
      );
    },
    onError: () => {
      if (snapshot.current) client.setQueryData(TASKS_KEY, snapshot.current);
    },
    onSettled: () => {
      snapshot.current = null;
      void client.invalidateQueries({ queryKey: TASKS_KEY });
    },
  });
}

/** Field edit (PATCH) and create/delete all live-fail loud via invalidate. */
export function usePatchTask() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, changes }: { id: string; changes: Partial<TaskDto> }) =>
      api.patchTask(id, changes),
    onSettled: () => void client.invalidateQueries({ queryKey: TASKS_KEY }),
  });
}

export function useCreateTask() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { id: string; title: string; type: TaskDto["type"]; important: boolean; urgent: boolean; estimate_blocks: number }) =>
      api.createTask(body),
    onSettled: () => void client.invalidateQueries({ queryKey: TASKS_KEY }),
  });
}

export function useDeleteTask() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteTask(id),
    onSettled: () => void client.invalidateQueries({ queryKey: TASKS_KEY }),
  });
}
