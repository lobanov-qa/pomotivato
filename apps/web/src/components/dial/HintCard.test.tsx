import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { HintDto } from "@/api/client";
import { HintCard } from "./HintCard";

/**
 * Hint card (spec 05 §3.6): the dictionary owns the text, the server the
 * kind; display order is fixed (diffuse first), task names resolve via
 * titleOf and degrade silently for unknown ids.
 */

const titleOf = (id: string | null | undefined) =>
  id === "t-9" ? "Chapters 3-4" : id === "t-x" ? "Task t-x" : "";

describe("HintCard", () => {
  it("renders nothing without hints", () => {
    render(<HintCard hints={[]} titleOf={titleOf} />);
    expect(screen.queryByTestId("hints.card")).not.toBeInTheDocument();
  });

  it("orders hints by the fixed sequence and names tasks", () => {
    const hints: HintDto[] = [
      { kind: "frog", params: { task_id: "t-9" } },
      { kind: "interleaving", params: { task_id: "t-x" } },
      { kind: "diffuse", params: {} },
    ];

    render(<HintCard hints={hints} titleOf={titleOf} />);

    const items = screen.getAllByTestId(/^hints\.card-/);
    expect(items.map((item) => item.getAttribute("data-testid"))).toEqual([
      "hints.card-diffuse",
      "hints.card-interleaving",
      "hints.card-frog",
    ]);
    expect(items[2]).toHaveTextContent("Chapters 3-4");
  });

  it("drops the name suffix for an unknown task id", () => {
    render(<HintCard hints={[{ kind: "einstellung", params: { task_id: "gone" } }]} titleOf={titleOf} />);

    expect(screen.getByTestId("hints.card-einstellung")).toHaveTextContent("Серия прерываний");
    expect(screen.getByTestId("hints.card-einstellung")).not.toHaveTextContent("задача");
  });
});
