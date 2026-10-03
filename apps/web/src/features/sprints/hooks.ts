/**
 * Sprint queries/mutations (spec 05 §3.10 / F10): the /week band is the
 * only sprint UI, so this hook file serves that one screen. Server owns
 * numbering and the overlap/active rules; failures surface as errors the
 * modal prints (409 texts come from the API).
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type SprintDto } from "@/api/client";

export const SPRINTS_KEY = ["sprints"] as const;

export function useSprints() {
  const query = useQuery({ queryKey: SPRINTS_KEY, queryFn: api.listSprints });
  const active = (query.data ?? []).find((sprint) => sprint.status === "active") ?? null;
  return { ...query, sprints: query.data ?? [], active };
}

export type SprintDraft = Pick<
  SprintDto,
  "name" | "goal" | "done_criteria" | "start_date" | "end_date"
>;

export function useCreateSprint() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (draft: SprintDraft) => api.createSprint(draft),
    onSettled: () => void client.invalidateQueries({ queryKey: SPRINTS_KEY }),
  });
}

export function usePatchSprint() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, changes }: { id: string; changes: Partial<SprintDto> }) =>
      api.patchSprint(id, changes),
    onSettled: () => void client.invalidateQueries({ queryKey: SPRINTS_KEY }),
  });
}

/** Sprint-day highlight for the week cells (band asks: is this date in?). */
export function useSprintDates(): (iso: string) => boolean {
  const { active } = useSprints();
  return (iso: string) =>
    active !== null && iso >= active.start_date && iso <= active.end_date;
}

/** The sprint card modal (spec 07 §4.1.4): detail = sprint + its tasks. */
export function useSprintDetail(id: string | null) {
  return useQuery({
    queryKey: ["sprints", id],
    queryFn: () => api.getSprintDetail(id as string),
    enabled: id !== null,
  });
}

/** V29: delete wipes the container WITH its cards (dialog owns the warning). */
export function useDeleteSprint() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteSprint(id),
    onSettled: () => {
      void client.invalidateQueries({ queryKey: SPRINTS_KEY });
      void client.invalidateQueries({ queryKey: ["tasks"] });
    },
  });
}

/** A40 menu per card: 'leave' freezes, target-or-null copies (server owns it). */
export function useCarryChoice() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ taskId, body }: { taskId: string; body: { target_sprint_id?: string | null; leave?: boolean } }) =>
      api.carryChoice(taskId, body),
    onSettled: () => {
      void client.invalidateQueries({ queryKey: SPRINTS_KEY });
      void client.invalidateQueries({ queryKey: ["tasks"] });
      void client.invalidateQueries({ queryKey: ["sprints"] });
    },
  });
}

/** «Оставить все как есть» (A40): bulk freeze, idempotent on the server. */
export function useCarryChoiceAll() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (sprintId: string) => api.carryChoiceAll(sprintId),
    onSettled: () => {
      void client.invalidateQueries({ queryKey: SPRINTS_KEY });
      void client.invalidateQueries({ queryKey: ["tasks"] });
      void client.invalidateQueries({ queryKey: ["sprints"] });
    },
  });
}
