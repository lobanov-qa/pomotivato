/**
 * E4b science wire types (spec 05 §3.6-§3.9): hints, the spaced-repetition
 * inbox and the frog answer. Shapes mirror api/schemas.py 1:1 — the server
 * computes kinds and data, the dictionary renders text, the client never
 * recalculates rules.
 */

export type HintKind = "diffuse" | "interleaving" | "overlearning" | "einstellung" | "frog";

export interface HintDto {
  kind: HintKind;
  params: Record<string, string | number>;
}

export interface RepetitionDueDto {
  task_id: string;
  title: string;
  interval_idx: number;
  next_due: string;
  overdue_days: number;
}

export interface FrogDto {
  task_id: string | null;
}
