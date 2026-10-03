/**
 * Sprint create/edit modal (spec 05 §3.10): name + goal + done_criteria +
 * period (date inputs, 1..14 days clamped client-side, V14 server-side).
 * For a planned sprint the "activate" verb lives here too; for the active
 * one — "complete". 409/422 server texts show as-is (they are RU already).
 */

import { useState } from "react";
import type { SprintDto } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import {
  useCreateSprint,
  useDeleteSprint,
  usePatchSprint,
  useSprintDetail,
  type SprintDraft,
} from "@/features/sprints/hooks";
import { t } from "@/i18n/ru";
import { SprintTasksBlock } from "./SprintTasksBlock";

interface Props {
  /** null -> create mode. */
  sprint: SprintDto | null;
  windowStart: string;
  /** Active sprints for the fate menu (A13: copies only into activated). */
  activeSprints?: SprintDto[];
  onClose: () => void;
}

function addDays(iso: string, days: number): string {
  const date = new Date(`${iso}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

export function SprintModal({ sprint, windowStart, activeSprints = [], onClose }: Props) {
  const create = useCreateSprint();
  const patch = usePatchSprint();
  const del = useDeleteSprint();
  // The card lists its tasks (spec 07 §4.1.4); the list endpoint omits them.
  const detail = useSprintDetail(sprint?.id ?? null);
  const tasks = detail.data?.tasks ?? [];
  // completed -> read-only texts (period frozen by the server too, §4.1.4).
  const frozen = sprint?.status === "completed";
  const active = sprint?.status === "active";
  // §4.2: delete warns about the cards it wipes; the fate menu lives in the
  // tasks block right here, so the dialog has a way out before deleting.
  const [askDelete, setAskDelete] = useState(false);
  async function confirmDelete(): Promise<void> {
    if (!sprint) return;
    try {
      await del.mutateAsync(sprint.id);
      onClose();
    } catch {
      /* the error line below shows the server text */
    }
  }
  const [draft, setDraft] = useState<SprintDraft>(() => ({
    name: sprint?.name ?? "",
    goal: sprint?.goal ?? "",
    done_criteria: sprint?.done_criteria ?? "",
    start_date: sprint?.start_date ?? windowStart,
    end_date: sprint?.end_date ?? addDays(windowStart, 6),
  }));
  const busy = create.isPending || patch.isPending || del.isPending;

  const invalid = draft.start_date > draft.end_date;
  const tooLong = !invalid && daysBetween(draft.start_date, draft.end_date) > 14;

  async function save(): Promise<void> {
    const body = {
      name: (draft.name ?? "").trim() || null,
      goal: (draft.goal ?? "").trim() || null,
      done_criteria: (draft.done_criteria ?? "").trim() || null,
      start_date: draft.start_date,
      end_date: draft.end_date,
    };
    try {
      if (sprint) await patch.mutateAsync({ id: sprint.id, changes: body });
      else await create.mutateAsync(body);
      onClose();
    } catch {
      /* the error line below shows the server text */
    }
  }

  async function setStatus(status: SprintDto["status"]): Promise<void> {
    if (!sprint) return;
    try {
      await patch.mutateAsync({ id: sprint.id, changes: { status } });
      onClose();
    } catch {
      /* rendered below */
    }
  }

  const serverError = create.error ?? patch.error ?? del.error ?? null;

  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4"
      data-testid="sprint.overlay"
      onClick={onClose}
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-label={t("sprint.title")}
        data-testid="sprint.modal"
        onClick={(event) => event.stopPropagation()}
        className="w-full max-w-sm rounded-card border bg-card p-4 shadow-card"
      >
        <h2 className="mb-3 text-sm font-semibold">
          {sprint ? `${t("sprint.title")} ${sprint.number}` : t("week.sprint-create")}
        </h2>
        <div className="flex flex-col gap-2">
          <Input
            data-testid="sprint.form-name"
            placeholder={t("sprint.name-placeholder")}
            maxLength={200}
            disabled={frozen}
            value={draft.name ?? ""}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
          />
          <Input
            data-testid="sprint.form-goal"
            placeholder={t("sprint.goal-placeholder")}
            maxLength={200}
            disabled={frozen}
            value={draft.goal ?? ""}
            onChange={(e) => setDraft({ ...draft, goal: e.target.value })}
          />
          <Input
            data-testid="sprint.form-done"
            placeholder={t("sprint.done-placeholder")}
            maxLength={200}
            disabled={frozen}
            value={draft.done_criteria ?? ""}
            onChange={(e) => setDraft({ ...draft, done_criteria: e.target.value })}
          />
          <div className="flex items-center gap-2">
            <Label htmlFor="sprint-start">{t("sprint.from")}</Label>
            <Input
              id="sprint-start"
              type="date"
              data-testid="sprint.form-start"
              disabled={frozen || active}
              value={draft.start_date}
              onChange={(e) => setDraft({ ...draft, start_date: e.target.value })}
            />
            <Label htmlFor="sprint-end">{t("sprint.to")}</Label>
            <Input
              id="sprint-end"
              type="date"
              data-testid="sprint.form-end"
              disabled={frozen || active}
              value={draft.end_date}
              onChange={(e) => setDraft({ ...draft, end_date: e.target.value })}
            />
          </div>
          <div className="flex gap-1">
            {[6, 13].map((span) => (
              <button
                key={span}
                type="button"
                data-testid={`sprint.preset-${span + 1}`}
                disabled={frozen || active}
                onClick={() => setDraft({ ...draft, end_date: addDays(draft.start_date, span) })}
                className="rounded-md border px-2 py-0.5 text-xs hover:bg-muted"
              >
                {span === 6 ? t("sprint.week1") : t("sprint.week2")}
              </button>
            ))}
          </div>
          {invalid || tooLong ? (
            <p className="text-xs text-danger" data-testid="sprint.form-error">
              {t("sprint.period-error")}
            </p>
          ) : serverError ? (
            <p className="text-xs text-danger" data-testid="sprint.form-error">
              {serverMessage(serverError)}
            </p>
          ) : null}
        </div>
        {sprint ? (
          <div className="mt-3 border-t pt-3" data-testid="sprint.tasks-zone">
            <SprintTasksBlock
              sprint={detail.data ?? sprint}
              tasks={tasks}
              activeSprints={activeSprints}
            />
            {frozen ? <p className="mt-1 text-xs text-muted-foreground">{t("sprint.readonly")}</p> : null}
          </div>
        ) : null}
        {askDelete ? (
          <div className="mt-4 flex flex-col gap-2" data-testid="sprint.delete-dialog">
            <p className="text-xs">{t("sprint.delete-warning", "ru", { count: tasks.length })}</p>
            <div className="flex gap-2">
              <Button variant="outline" data-testid="sprint.delete-confirm" onClick={() => void confirmDelete()}>
                {t("sprint.delete-confirm")}
              </Button>
              <Button variant="ghost" data-testid="sprint.delete-cancel" onClick={() => setAskDelete(false)}>
                {t("common.cancel")}
              </Button>
            </div>
          </div>
        ) : (
        <div className="mt-4 flex gap-2">
          <Button
            data-testid="sprint.save"
            disabled={busy || invalid || tooLong || frozen}
            onClick={() => void save()}
          >
            {t("settings.save")}
          </Button>
          {sprint?.status === "planned" && (
            <Button
              variant="outline"
              data-testid="sprint.submit-activate"
              disabled={busy}
              onClick={() => void setStatus("active")}
            >
              {t("sprint.activate")}
            </Button>
          )}
          {sprint?.status === "active" && (
            <Button
              variant="outline"
              data-testid="sprint.submit-complete"
              disabled={busy}
              onClick={() => void setStatus("completed")}
            >
              {t("sprint.complete")}
            </Button>
          )}
          {sprint ? (
            <Button
              variant="ghost"
              data-testid="sprint.delete"
              disabled={busy}
              onClick={() => setAskDelete(true)}
            >
              {t("sprint.delete")}
            </Button>
          ) : null}
          <Button variant="ghost" data-testid="sprint.cancel" onClick={onClose}>
            {t("common.cancel")}
          </Button>
        </div>
        )}
      </section>
    </div>
  );
}

function daysBetween(start: string, end: string): number {
  const ms = new Date(`${end}T00:00:00Z`).getTime() - new Date(`${start}T00:00:00Z`).getTime();
  return Math.round(ms / 86_400_000) + 1;
}

function serverMessage(error: unknown): string {
  // ApiError already carries the server's {detail:{message}} string.
  return error instanceof Error && error.message ? error.message : t("settings.error");
}
