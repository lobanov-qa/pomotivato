/**
 * Sprint list under the day grid (spec 07 §4.1.3, E4c PR 7). Rows: planned
 * gray, active in its color, completed gray and read-only; the current
 * sprint gets a star and a bold frame; a completed sprint with undecided
 * fates carries the "!" badge. The "Archive" button above the list is the
 * page entrance (§4.8).
 */

import { useState } from "react";
import { Link } from "react-router-dom";
import type { SprintDto } from "@/api/client";
import { useSprints } from "@/features/sprints/hooks";
import {
  hasUndecidedFate,
  sprintColor,
  sprintList,
  sprintStatusKey,
} from "@/features/sprints/colors";
import { t } from "@/i18n/ru";
import { cn } from "@/lib/utils";
import { todayIso } from "@/features/week/dates";
import { SprintModal } from "./SprintModal";

/**
 * Self-contained section: the row click opens the sprint card right here
 * (a second owner of the same modal as the band — the sections never show
 * simultaneously, and lifting the state to WeekScreen would only spread
 * the wiring without sharing a view).
 */
export function SprintList() {
  const { sprints } = useSprints();
  const [open, setOpen] = useState<SprintDto | null>(null);
  const today = todayIso();
  const rows = sprintList(sprints, today);
  return (
    <section className="flex flex-col gap-1" data-testid="sprint.list">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          {t("sprint.list-title")}
        </h2>
        <Link
          to="/archive"
          data-testid="sprint.archive-link"
          className="rounded-md border px-2 py-0.5 text-xs hover:bg-muted"
        >
          {t("sprint.archive")}
        </Link>
      </div>
      {rows.length === 0 && <p className="text-xs text-muted-foreground">{t("sprint.list-empty")}</p>}
      {rows.map((sprint) => {
        const color = sprintColor(sprint);
        return (
          <div
            key={sprint.id}
            data-testid={`sprint.row-${sprint.id}`}
            className={cn(
              "flex items-center gap-2 rounded-card border bg-card px-3 py-1.5 text-sm",
              color ? cn(color.border, color.fill) : "border-border",
              sprint.is_current && "border-2 font-semibold",
            )}
          >
            <button
              type="button"
              data-testid={`sprint.row-open-${sprint.id}`}
              onClick={() => setOpen(sprint)}
              className="flex flex-1 items-center gap-2 text-left hover:underline"
            >
              {sprint.is_current && <span aria-hidden="true">★</span>}
              <span>{`${t("sprint.title")} ${sprint.number}${sprint.name ? ` — ${sprint.name}` : ""}`}</span>
              <span className="text-xs tabular-nums text-muted-foreground">
                {sprint.start_date} → {sprint.end_date}
              </span>
              <span className="text-xs text-muted-foreground">
                {t(`sprint.status-${sprintStatusKey(sprint, today)}` as "sprint.status-created")}
              </span>
            </button>
            {hasUndecidedFate(sprint) && (
              <span
                data-testid={`sprint.fate-badge-${sprint.id}`}
                title={t("sprint.fate-badge")}
                className="rounded-full bg-danger/15 px-2 text-xs font-bold text-danger"
              >
                !
              </span>
            )}
          </div>
        );
      })}
      {open && (
        <SprintModal
          sprint={open}
          windowStart={open.start_date}
          activeSprints={sprints.filter((sp) => sp.status === "active")}
          onClose={() => setOpen(null)}
        />
      )}
    </section>
  );
}
