/**
 * Review modal (spec 03 §2 + E4b §3.7 + E4c V24): score 1..5 + optional
 * comment for the work block that just closed; STUDY blocks additionally
 * ask for active recall (three facts from memory). The habit reward retired
 * with DF7 (spec 06, author 08.09). The FSM never blocks for a review — the
 * timer keeps running behind the overlay. "Пропустить" (A18/A39, replaced
 * the old "Позже" dismissal) posts an explicit score=null: the verdict is
 * final for this block, the card still walks by V22, stats receive a hole.
 */

import { useState } from "react";
import type { TaskType } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { t } from "@/i18n/ru";
import { cn } from "@/lib/utils";

export interface ReviewPayload {
  score: number | null;
  comment?: string;
  recall_notes?: string;
}

interface Props {
  taskTitle: string;
  taskType: TaskType;
  onSubmit: (payload: ReviewPayload) => Promise<void>;
}

export function ReviewModal({ taskTitle, taskType, onSubmit }: Props) {
  const [score, setScore] = useState<number | null>(null);
  const [comment, setComment] = useState("");
  const [recall, setRecall] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(payload: ReviewPayload): Promise<void> {
    if (submitting) return;
    setSubmitting(true);
    try {
      await onSubmit({
        ...payload,
        comment: payload.comment ?? (comment.trim() || undefined),
        recall_notes: taskType === "study" ? recall.trim() || undefined : undefined,
      });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/45 backdrop-blur-sm"
      data-testid="review.overlay"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t("review.title")}
        className="w-[min(420px,92vw)] rounded-card border bg-card p-6 text-center shadow-card-drag"
        data-testid="review.modal"
      >
        <p className="text-xs uppercase tracking-[0.25em] text-muted-foreground">
          {t("review.kick")}
        </p>
        <h3 className="mt-1 text-lg font-semibold">{t("review.title")}</h3>
        <p className="mt-1 truncate text-sm text-muted-foreground" data-testid="review.task">
          {taskTitle}
        </p>
        <div className="mt-5 flex justify-center gap-2" role="radiogroup" aria-label={t("review.title")}>
          {[1, 2, 3, 4, 5].map((value) => (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={score === value}
              data-testid={`review.scale-${value}`}
              onClick={() => setScore(value)}
              className={cn(
                "h-12 w-12 rounded-lg border text-lg font-semibold transition-all",
                score === value
                  ? "border-primary bg-primary text-primary-foreground shadow-card-hover"
                  : "bg-muted/40 hover:bg-muted",
              )}
            >
              {value}
            </button>
          ))}
        </div>
        <div className="mt-1 flex justify-between px-2 text-[10px] text-muted-foreground">
          <span>{t("review.scale-min")}</span>
          <span>{t("review.scale-max")}</span>
        </div>
        {taskType === "study" && (
          <label className="mt-4 flex flex-col gap-1 text-left">
            <span className="text-xs text-muted-foreground">{t("review.recall-label")}</span>
            <Textarea
              data-testid="review.recall-notes"
              placeholder={t("review.recall-placeholder")}
              value={recall}
              onChange={(e) => setRecall(e.target.value)}
            />
          </label>
        )}
        <Textarea
          data-testid="review.comment"
          placeholder={t("review.comment-placeholder")}
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          className={taskType === "normal" ? "mt-4 text-left" : "mt-2 text-left"}
        />
        <div className="mt-4 flex justify-center gap-2">
          {/* A39 (spec 07 §2.7): skip is a verdict now, not a postponement —
              it posts score=null and the card walks like on a real score.
              The old "Позже" (local hide, reopen later) is retired with it. */}
          <Button
            variant="ghost"
            data-testid="review.skip"
            disabled={submitting}
            onClick={() => void submit({ score: null })}
          >
            {t("review.skip")}
          </Button>
          <Button
            data-testid="review.submit"
            disabled={score === null || submitting}
            onClick={() => score !== null && void submit({ score })}
          >
            {t("review.submit")}
          </Button>
        </div>
      </div>
    </div>
  );
}
