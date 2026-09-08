/**
 * Break-time hint card (spec 05 §3.6 / F6): renders server hint kinds via
 * the RU dictionary. NEVER overlays the dial: it sits below the controls
 * and only while the phase is a rest phase (the parent guards that).
 * Params carry data (task ids); the card resolves names when it has the
 * task catalog, otherwise it drops the suffix honestly.
 */

import type { HintDto } from "@/api/client";
import { t } from "@/i18n/ru";

interface Props {
  hints: HintDto[];
  titleOf: (taskId: string | null | undefined) => string;
}

const ORDER = ["diffuse", "interleaving", "overlearning", "einstellung", "frog"] as const;

export function HintCard({ hints, titleOf }: Props) {
  if (hints.length === 0) return null;
  const sorted = [...hints].sort(
    (a, b) => ORDER.indexOf(a.kind) - ORDER.indexOf(b.kind),
  );
  return (
    <aside
      className="w-full max-w-md rounded-card border bg-card p-3 shadow-card"
      data-testid="hints.card"
      aria-label={t("hints.card-title")}
    >
      <p className="mb-1 text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
        {t("hints.card-title")}
      </p>
      <ul className="flex flex-col gap-1">
        {sorted.map((hint) => (
          <li
            key={hint.kind + String(hint.params.task_id ?? "")}
            data-testid={`hints.card-${hint.kind}`}
            className="text-sm leading-snug"
          >
            {t(`hints.kind-${hint.kind}` as "hints.kind-diffuse")}
            {typeof hint.params.task_id === "string" && titleOf(hint.params.task_id) && (
              <span className="block text-xs text-muted-foreground">
                {t("hints.task-suffix")}: {titleOf(hint.params.task_id)}
              </span>
            )}
          </li>
        ))}
      </ul>
    </aside>
  );
}
