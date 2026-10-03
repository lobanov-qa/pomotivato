/**
 * Board scope (spec 07 §4.3, E4c PR 5): the sprint selector replaces the
 * "This week / All" filter. A scope is an ACTIVATED sprint id or the
 * dateless "no sprint" shelf (null). The selection decides the columns'
 * content entirely — and only their display: the day-plan sync reads the
 * full task list (spec 07 §10.1: filtering syncPlan by the visible scope
 * would wipe other scopes' slots on every switch).
 */

import type { SprintDto, TaskDto } from "@/api/client";

export type ScopeId = string | null;

/** Scope values travel in the URL: a sprint id, or "none" for the shelf. */
export function scopeToParam(scope: ScopeId): string {
  return scope ?? "none";
}

export function scopeFromParam(param: string | null): ScopeId | undefined {
  // undefined means "no/foreign parameter" — the fallback picks the scope.
  if (param === null) return undefined;
  return param === "none" ? null : param;
}

/** The `?sprint=` URL parameter (spec 07 §4.3): survives reload and a
 * shared link. The history API is used directly (no router coupling in
 * jsdom tests; the app runs under createBrowserRouter anyway, the query
 * string is real location data there too). */
export function readScopeParam(): ScopeId | undefined {
  return scopeFromParam(new URLSearchParams(window.location.search).get("sprint"));
}

export function writeScopeParam(scope: ScopeId): void {
  const url = new URL(window.location.href);
  url.searchParams.set("sprint", scopeToParam(scope));
  window.history.replaceState({}, "", url);
}

/** A shelf card has no owner; a scoped card belongs to its container. */
export function withinScope(task: TaskDto, scope: ScopeId): boolean {
  return task.sprint_id === scope;
}

/** Selector options: activated sprints only (A13) plus the shelf, in the
 * server's order (newest number first). */
export function scopeOptions(
  sprints: readonly SprintDto[],
): { value: ScopeId; label: string }[] {
  return [
    ...sprints
      .filter((sprint) => sprint.status === "active")
      .map((sprint) => ({
        value: sprint.id as ScopeId,
        label: `#${sprint.number}${sprint.name ? ` · ${sprint.name}` : ""}`,
      })),
    { value: null, label: "shelf" }, // localized by the caller (kanban.scope-none)
  ];
}

/** Default scope (spec 4.3): the sprint covering today, else the shelf. */
export function defaultScope(
  sprints: readonly SprintDto[],
  todayIso: string,
  saved: ScopeId | undefined,
): ScopeId {
  const activeIds = new Set(
    sprints.filter((sprint) => sprint.status === "active").map((sprint) => sprint.id),
  );
  if (saved !== undefined && (saved === null || activeIds.has(saved))) return saved;
  const current = sprints.find(
    (sprint) =>
      sprint.status === "active" &&
      sprint.start_date <= todayIso &&
      sprint.end_date >= todayIso,
  );
  return current?.id ?? null;
}

/** Deep link from the sprint card (E4c §4.1.4): ?task=<id> opens the panel. */
export function readTaskParam(): string | null {
  return new URLSearchParams(window.location.search).get("task");
}

export function clearTaskParam(): void {
  const url = new URL(window.location.href);
  url.searchParams.delete("task");
  window.history.replaceState({}, "", url);
}
