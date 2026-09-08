/**
 * Break-time hints + spaced-repetition inbox (spec 05 §3.6-3.7): the dial
 * refetches hints on every phase change (the server folds the live session
 * phase into the answer — no second timer logic in the browser); the week
 * screen reads the due queue. Both are read-only GETs: "add to plan" reuses
 * the day-activation endpoint (POST add) from PR5's client.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type HintDto, type RepetitionDueDto } from "@/api/client";

export const HINTS_KEY = ["hints"] as const;
export const DUE_KEY = ["repetitions", "due"] as const;

export function useHints(enabled: boolean) {
  return useQuery({
    queryKey: HINTS_KEY,
    queryFn: api.getHints,
    enabled,
    // phase_changed drives explicit refetches; the query itself stays quiet
    staleTime: Infinity,
  });
}

export function useDueRepetitions() {
  return useQuery({ queryKey: DUE_KEY, queryFn: () => api.getRepetitionDue() });
}

/** One due card -> plan the task into today (spec 05 §3.7 button). */
export function useAddDueToToday() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (taskId: string) => {
      const date = new Date().toLocaleDateString("en-CA");
      return api.addTaskToPlan(date, taskId);
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: DUE_KEY });
      void client.invalidateQueries({ queryKey: ["tasks"] });
    },
  });
}

export type { HintDto, RepetitionDueDto };
