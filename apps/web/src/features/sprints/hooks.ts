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
