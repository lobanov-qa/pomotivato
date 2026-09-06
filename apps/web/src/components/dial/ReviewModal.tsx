/**
 * Review modal (spec 03 §2): score 1..5 + optional comment for the work
 * block that just closed. The FSM never blocks for a review — the timer
 * keeps running behind the overlay; "Позже" dismisses and the block stays
 * reviewable while the session lives (the modal reopens on the next
 * closed-but-unreviewed segment only).
 */

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { t } from "@/i18n/ru";
import { cn } from "@/lib/utils";

interface Props {
  taskTitle: string;
  onSubmit: (score: number, comment: string | undefined) => Promise<void>;
  onDismiss: () => void;
}

export function ReviewModal({ taskTitle, onSubmit, onDismiss }: Props) {
  const [score, setScore] = useState<number | null>(null);
  const [comment, setComment] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(): Promise<void> {
    if (score === null || submitting) return;
    setSubmitting(true);
    try {
      await onSubmit(score, comment.trim() || undefined);
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
        <Textarea
          data-testid="review.comment"
          placeholder={t("review.comment-placeholder")}
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          className="mt-4 text-left"
        />
        <div className="mt-4 flex justify-center gap-2">
          <Button variant="ghost" data-testid="review.dismiss" onClick={onDismiss}>
            {t("review.dismiss")}
          </Button>
          <Button
            data-testid="review.submit"
            disabled={score === null || submitting}
            onClick={() => void submit()}
          >
            {t("review.submit")}
          </Button>
        </div>
      </div>
    </div>
  );
}
