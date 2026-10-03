/**
 * Sprint band on /week (spec 05 §3.10, ⚑ Q8): the header strip shows the
 * active sprint and lights its days; no active sprint -> "Create" button.
 * Everything sprint-y lives on this one screen — no separate page (author
 * decision), editing through the modal below.
 */

import { useState } from "react";
import type { SprintDto } from "@/api/client";
import { sprintColor, sprintStatusKey } from "@/features/sprints/colors";
import { useSprints } from "@/features/sprints/hooks";
import { todayIso } from "@/features/week/dates";
import { t } from "@/i18n/ru";
import { cn } from "@/lib/utils";
import { SprintModal } from "./SprintModal";

interface Props {
  /** ISO dates of the visible window: the band dims the sprint's days. */
  windowDates: string[];
  /** Row/list opener handed the sprint card (E4c PR 7, §4.1.3). */
  onOpen?: (sprint: SprintDto) => void;
}

export function SprintBand({ windowDates, onOpen }: Props) {
  const { active, sprints } = useSprints();
  const [modal, setModal] = useState<null | { sprint: SprintDto | null }>(null);
  // The band can also edit the newest planned sprint when none is active.
  const shown = active ?? sprints.find((sprint) => sprint.status === "planned") ?? null;
  const inWindow = shown
    ? windowDates.filter((iso) => iso >= shown.start_date && iso <= shown.end_date).length
    : 0;
  // §4.1.1: the band wears the sprint's color (planned/completed stay gray)
  // and writes the textual status next to the period.
  const color = shown ? sprintColor(shown) : null;

  return (
    <div
      data-testid="week.sprint-band"
      className={cn(
        "flex flex-wrap items-center gap-2 rounded-card border px-3 py-1.5 text-sm",
        color ? cn(color.border, color.fill) : "bg-card",
      )}
    >
      {shown ? (
        <>
          <button
            type="button"
            data-testid="week.sprint-edit"
            onClick={() => (onOpen ? onOpen(shown) : setModal({ sprint: shown }))}
            className="font-semibold hover:underline"
          >
            {`${t("sprint.title")} ${shown.number}`}
            {shown.name ? ` — ${shown.name}` : ""}
          </button>
          <span className="text-xs tabular-nums text-muted-foreground">
            {shown.start_date} → {shown.end_date}
            {inWindow > 0 && ` · ${inWindow}`}
          </span>
          <span className="text-xs text-muted-foreground">
            {t(`sprint.status-${sprintStatusKey(shown, todayIso())}` as "sprint.status-created")}
          </span>
          {shown.goal && <span className="truncate text-xs">{shown.goal}</span>}
        </>
      ) : (
        <span className="text-muted-foreground">{t("week.sprint-none")}</span>
      )}
      <div className="ml-auto flex gap-2">
        {shown && shown.status === "planned" && (
          <button
            type="button"
            data-testid="week.sprint-activate"
            onClick={() => setModal({ sprint: shown })}
            className="rounded-md border border-primary px-2 py-0.5 text-xs text-primary hover:bg-primary/10"
          >
            {t("sprint.activate")}
          </button>
        )}
        {active && (
          <button
            type="button"
            data-testid="week.sprint-complete"
            onClick={() => setModal({ sprint: active })}
            className="rounded-md border px-2 py-0.5 text-xs hover:bg-muted"
          >
            {t("sprint.complete")}
          </button>
        )}
        {!shown && (
          <button
            type="button"
            data-testid="week.sprint-create"
            onClick={() => setModal({ sprint: null })}
            className="rounded-md border border-primary px-2 py-0.5 text-xs text-primary hover:bg-primary/10"
          >
            {t("week.sprint-create")}
          </button>
        )}
      </div>
      {modal && (
        <SprintModal
          sprint={modal.sprint}
          windowStart={windowDates[0]}
          activeSprints={sprints.filter((sp) => sp.status === "active")}
          onClose={() => setModal(null)}
        />
      )}
    </div>
  );
}
