import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ReviewModal } from "./ReviewModal";

/**
 * The review modal contract (spec 03 §2 + E4b §3.7 + E4c V24): score 1..5
 * + optional comment, submit disabled until a score is picked; "Пропустить"
 * is a VERDICT, not a dismissal — it sends score=null (A18/A39) and the
 * card walks exactly like on a real score. STUDY grows the active-recall
 * box; NORMAL shows neither (DF7 of spec 05: the modal must not nag).
 */

function renderModal(taskType: "normal" | "study" = "normal") {
  const onSubmit = vi.fn().mockResolvedValue(undefined);
  render(<ReviewModal taskTitle="Deep work" taskType={taskType} onSubmit={onSubmit} />);
  return { onSubmit };
}

describe("ReviewModal", () => {
  it("shows the task and the 1..5 scale with RU anchors", () => {
    renderModal();

    expect(screen.getByTestId("review.task")).toHaveTextContent("Deep work");
    for (const value of [1, 2, 3, 4, 5]) {
      expect(screen.getByTestId(`review.scale-${value}`)).toBeInTheDocument();
    }
    expect(screen.getByText("вяло")).toBeInTheDocument();
    expect(screen.getByText("в потоке")).toBeInTheDocument();
  });

  it("submit is disabled until a score is chosen", async () => {
    const user = userEvent.setup();
    renderModal();

    expect(screen.getByTestId("review.submit")).toBeDisabled();
    await user.click(screen.getByTestId("review.scale-4"));
    expect(screen.getByTestId("review.submit")).toBeEnabled();
    expect(screen.getByTestId("review.scale-4")).toHaveAttribute("aria-checked", "true");
  });

  it("sends score and trimmed comment on submit", async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderModal();

    await user.click(screen.getByTestId("review.scale-5"));
    await user.type(screen.getByTestId("review.comment"), "  в потоке!  ");
    await user.click(screen.getByTestId("review.submit"));

    expect(onSubmit).toHaveBeenCalledWith({ score: 5, comment: "в потоке!" });
  });

  it("omits blank fields and hides science inputs for normal tasks", async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderModal();

    expect(screen.queryByTestId("review.recall-notes")).not.toBeInTheDocument();
    await user.click(screen.getByTestId("review.scale-3"));
    await user.click(screen.getByTestId("review.submit"));

    expect(onSubmit).toHaveBeenCalledWith({ score: 3 });
  });

  it("study review carries active-recall notes", async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderModal("study");

    await user.click(screen.getByTestId("review.scale-4"));
    await user.type(screen.getByTestId("review.recall-notes"), "  A, B, C  ");
    await user.click(screen.getByTestId("review.submit"));

    expect(onSubmit).toHaveBeenCalledWith({ score: 4, recall_notes: "A, B, C" });
  });

  it("skip posts the null verdict without a chosen score (V24/A39)", async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderModal();

    await user.click(screen.getByTestId("review.skip"));

    expect(onSubmit).toHaveBeenCalledWith({ score: null });
  });

  it("skip is available while no score is picked (it is a verdict, not a delay)", () => {
    renderModal();

    expect(screen.getByTestId("review.skip")).toBeEnabled();
    expect(screen.queryByTestId("review.dismiss")).not.toBeInTheDocument();
  });
});
