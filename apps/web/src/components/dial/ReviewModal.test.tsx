import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ReviewModal } from "./ReviewModal";

/**
 * The review modal contract (spec 03 §2): score 1..5 + optional comment,
 * submit disabled until a score is picked, "Позже" dismisses (the FSM
 * never blocks — the timer runs behind the overlay).
 */

function renderModal() {
  const onSubmit = vi.fn().mockResolvedValue(undefined);
  const onDismiss = vi.fn();
  render(
    <ReviewModal taskTitle="Deep work" onSubmit={onSubmit} onDismiss={onDismiss} />,
  );
  return { onSubmit, onDismiss };
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

    expect(onSubmit).toHaveBeenCalledWith(5, "в потоке!");
  });

  it("omits a blank comment", async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderModal();

    await user.click(screen.getByTestId("review.scale-3"));
    await user.click(screen.getByTestId("review.submit"));

    expect(onSubmit).toHaveBeenCalledWith(3, undefined);
  });

  it("dismiss closes without a score", async () => {
    const user = userEvent.setup();
    const { onDismiss, onSubmit } = renderModal();

    await user.click(screen.getByTestId("review.dismiss"));

    expect(onDismiss).toHaveBeenCalled();
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
