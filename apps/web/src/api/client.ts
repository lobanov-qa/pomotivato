/**
 * Typed transport over the FastAPI backend (spec 02 §5 / spec 03 §5).
 *
 * Shapes mirror api/schemas.py exactly; the server stays the single source
 * of truth, this client adds no logic beyond URL building and the JSON
 * error envelope. SSE consumption lives in the dial PR (spec 03 §4).
 */

export type TaskStatus = "backlog" | "planned" | "doing" | "done" | "archived";
export type TaskType = "normal" | "study" | "habit";

export interface TaskDto {
  id: string;
  title: string;
  type: TaskType;
  important: boolean;
  urgent: boolean;
  status: TaskStatus;
  estimate_blocks: number;
  recurrence: Record<string, unknown>;
  deadline: string | null;
  parent_id: string | null;
  when_then: string | null;
  done_criteria: string | null;
  benefit: string | null;
  created_at: string;
}

export interface SpecialBreakDto {
  /** Wall time "HH:MM" in the machine's local zone (spec 05 ⚑ Q2). */
  at: string;
  duration_min: number;
  label: string;
}

export interface SessionSettingsDto {
  work_min: number;
  break_min: number;
  long_break_min: number;
  long_break_every: number;
  auto_start_next: boolean;
  // E4b modes (spec 05 §3.3-3.5).
  strict_mode: boolean;
  warmup_min: number;
  special_breaks: SpecialBreakDto[];
}

export type ThemeName = "auto" | "light" | "dark";

export interface UiSettingsDto {
  max_in_work: number;
  theme: ThemeName;
  require_science_fields: boolean;
}

export interface SettingsBundleDto {
  session: SessionSettingsDto;
  ui: UiSettingsDto;
}

export interface SegmentDto {
  id: string;
  session_id: string;
  phase: string;
  planned_min: number;
  task_id: string | null;
  started_at: string | null;
  ended_at: string | null;
  status: string | null;
}

export interface SessionDto {
  id: string;
  day_plan_id: string;
  state: string;
  started_at: string | null;
  stop_reason: string | null;
  phase: string | null;
  remaining_sec: number;
  phase_ends_at: string | null;
  average_score: number | null;
  settings: SessionSettingsDto;
  timeline: SegmentDto[];
  reviews: { segment_id: string; score: number; comment: string | null }[];
  /** Frozen slot snapshot (spec 01 v0.3): dial sectors; null = legacy row. */
  slots: SlotDto[] | null;
}

export interface SlotDto {
  sector: number;
  task_id: string;
}

export interface DayPlanDto {
  id: string;
  date: string;
  slots: SlotDto[];
}

export interface StatusDto {
  active: boolean;
  session_id?: string | null;
  state?: string | null;
  phase?: string | null;
  remaining_sec?: number | null;
  server_now: string;
  date: string;
}

export interface DailySummaryDto {
  date: string;
  blocks_done: number;
  blocks_planned: number;
  focus_min: number;
  average_score: number | null;
  reviews_count: number;
  tasks_done: number;
}

/* Stats/week DTOs live in ./types_stats (300-line split). Imported for
 * method signatures and re-exported so existing `from "./api/client"`
 * paths keep working (E3 lesson: aliases on Cyrillic paths are fragile). */
import type { FrogDto, HintDto, RepetitionDueDto } from "./types_science";
import type { AddResultDto, SprintDto, StatsDto, WeekDto } from "./types_stats";

export type { FrogDto, HintDto, HintKind, RepetitionDueDto } from "./types_science";

export type {
  ChartLabels,
  DaySlotDto,
  DaySummaryDto,
  EstimateVsFactDto,
  FactPointDto,
  GoalDepthRowDto,
  HeatmapCellDto,
  ParentProgressDto,
  PlannedDto,
  QuadrantKey,
  QuadrantRowDto,
  StatsDto,
  StatsPeriodDto,
  StatsTotalsDto,
  StreakDto,
  SprintDto,
  AddResultDto,
  WeekDayDto,
  WeekDto,
  ZombieItemDto,
  ZombiesDto,
} from "./types_stats";

/** Export endpoint answers files, not JSON (spec 04 §4.3); default window
 * is server-side, so empty params mean "last 30 days" on the wire too. */
export function exportUrl(format: "json" | "csv", from?: string, to?: string): string {
  const params = new URLSearchParams({ format });
  if (from) params.set("from", from);
  if (to) params.set("to", to);
  return `/api/export?${params.toString()}`;
}

/** Stable error codes from the server envelope detail.code (spec 02 §5). */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method,
    headers: body === undefined ? {} : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const fallback = new ApiError(response.status, "unknown", response.statusText);
    let payload: unknown;
    try {
      payload = await response.json();
    } catch {
      throw fallback;
    }
    const detail = (payload as { detail?: { code?: string; message?: string } })?.detail;
    if (typeof detail === "string") {
      // FastAPI validation errors: {detail: [{loc,msg,...}]} — keep code 422.
      throw new ApiError(response.status, "validation", "Проверь поля формы.");
    }
    if (!detail?.code) throw fallback;
    throw new ApiError(response.status, detail.code, detail.message ?? fallback.message);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  listTasks: (status?: TaskStatus) =>
    request<TaskDto[]>("GET", `/api/tasks${status ? `?status=${status}` : ""}`),
  createTask: (body: Partial<TaskDto> & { id: string; title: string }) =>
    request<TaskDto>("POST", "/api/tasks", body),
  patchTask: (id: string, changes: Partial<TaskDto>) =>
    request<TaskDto>("PATCH", `/api/tasks/${id}`, changes),
  setTaskStatus: (id: string, to: TaskStatus) =>
    request<TaskDto>("POST", `/api/tasks/${id}/status`, { to }),
  deleteTask: (id: string) => request<void>("DELETE", `/api/tasks/${id}`),

  getDayPlan: (date: string) => request<DayPlanDto>("GET", `/api/day-plans/${date}`),
  putDayPlan: (plan: DayPlanDto) =>
    request<DayPlanDto>("PUT", `/api/day-plans/${plan.date}`, plan),
  moveSlot: (date: string, from: number, to: number) =>
    request<DayPlanDto>("POST", `/api/day-plans/${date}/slots/move`, { from, to }),

  removeSlot: (date: string, sector: number) =>
    request<DayPlanDto>("DELETE", `/api/day-plans/${date}/slots/${sector}`),

  clearDayPlan: (date: string) => request<void>("DELETE", `/api/day-plans/${date}`),
  /** Drag-to-plan primitive (spec 05 §3.8): append the task's chunk. */
  addTaskToPlan: (date: string, taskId: string) =>
    request<AddResultDto>("POST", `/api/day-plans/${date}/add`, { task_id: taskId }),
  /** Materialize the date's recurring tasks into its plan (spec 05 §3.2). */
  activatePlan: (date: string) => request<AddResultDto>("POST", `/api/day-plans/${date}/activate`),

  listSprints: () => request<SprintDto[]>("GET", "/api/sprints"),
  createSprint: (body: {
    name?: string | null;
    goal?: string | null;
    done_criteria?: string | null;
    start_date: string;
    end_date: string;
  }) => request<SprintDto>("POST", "/api/sprints", body),
  patchSprint: (id: string, changes: Partial<SprintDto>) =>
    request<SprintDto>("PATCH", `/api/sprints/${id}`, changes),

  startSession: (body: { day_plan_id: string; settings?: Partial<SessionSettingsDto> }) =>
    request<SessionDto>("POST", "/api/sessions", body),
  getSession: (id: string) => request<SessionDto>("GET", `/api/sessions/${id}`),
  pauseSession: (id: string) => request<SessionDto>("POST", `/api/sessions/${id}/pause`),
  resumeSession: (id: string) => request<SessionDto>("POST", `/api/sessions/${id}/resume`),
  stopSession: (id: string) => request<SessionDto>("POST", `/api/sessions/${id}/stop`),
  skipBreak: (id: string) => request<SessionDto>("POST", `/api/sessions/${id}/skip-break`),
  sessionEventsUrl: (id: string) => `/api/sessions/${id}/events`,

  submitReview: (body: {
    segment_id: string;
    score: number;
    comment?: string;
    // E4b (spec 05 §3.7-3.8): study recall notes / habit reward.
    recall_notes?: string;
    reward?: string;
  }) =>
    request<{ segment_id: string; score: number }>("POST", "/api/reviews", body),

  getSettings: () => request<SettingsBundleDto>("GET", "/api/settings"),
  putSessionSettings: (settings: SessionSettingsDto) =>
    request<SessionSettingsDto>("PUT", "/api/settings/session", settings),
  putUiSettings: (ui: UiSettingsDto) => request<UiSettingsDto>("PUT", "/api/settings/ui", ui),
  /** The "eat the frog" candidate id (core rule, server-computed): the
   * kanban badge must not re-implement frog_candidate in TS. */
  getFrog: () => request<FrogDto>("GET", "/api/frog"),

  /** Break-time learning-science hints (spec 05 §3.6): kinds+params only. */
  getHints: () => request<HintDto[]>("GET", "/api/hints"),
  /** Spaced-repetition inbox due on/before `asOf` (spec 05 §3.7). */
  getRepetitionDue: (asOf?: string) => {
    const query = asOf ? `?as_of=${asOf}` : "";
    return request<RepetitionDueDto[]>("GET", `/api/repetitions/due${query}`);
  },

  getStatus: () => request<StatusDto>("GET", "/api/status"),
  getSummary: (date: string) => request<DailySummaryDto>("GET", `/api/summary/${date}`),

  getStats: (from?: string, to?: string) => {
    const params = new URLSearchParams();
    if (from) params.set("from", from);
    if (to) params.set("to", to);
    const query = params.toString();
    return request<StatsDto>("GET", `/api/stats${query ? `?${query}` : ""}`);
  },
  getWeek: (start?: string, days = 7) => {
    const params = new URLSearchParams({ days: String(days) });
    if (start) params.set("start", start);
    return request<WeekDto>("GET", `/api/week?${params.toString()}`);
  },
};
