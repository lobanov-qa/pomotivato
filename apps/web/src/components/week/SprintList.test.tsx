/**
 * Sprint list screen level (spec 07 §4.1.3/§4.1.4, E4c PR 7): the row set,
 * the "!" badge, the card modal in read-only completed mode and the fate
 * menu posting the A40 choice.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SprintList } from "./SprintList";

const posted: { url: string; method: string; body: unknown }[] = [];

const ACTIVE = {
  id: "s-act",
  number: 1,
  name: "w40",
  start_date: "2026-01-01",
  end_date: "2026-12-31",
  goal: null,
  done_criteria: null,
  status: "active",
  unfinished_count: 1,
  carry_pending: 0,
  is_current: true,
};

const COMPLETED = {
  id: "s-old",
  number: 2,
  name: null,
  start_date: "2025-01-01",
  end_date: "2025-01-07",
  goal: null,
  done_criteria: null,
  status: "completed",
  unfinished_count: 1,
  carry_pending: 1,
  is_current: false,
};

const PLANNED = {
  id: "s-plan",
  number: 3,
  name: null,
  start_date: "2027-01-01",
  end_date: "2027-01-07",
  goal: null,
  done_criteria: null,
  status: "planned",
  unfinished_count: 0,
  carry_pending: 0,
  is_current: false,
};

const CARD = {
  id: "c-1",
  title: "Undecided card",
  type: "normal",
  important: false,
  urgent: false,
  status: "planned",
  estimate_blocks: 1,
  recurrence: { kind: "once" },
  deadline: null,
  parent_id: null,
  when_then: null,
  done_criteria: null,
  benefit: null,
  cloned_from: null,
  no_timer: false,
  sprint_id: "s-old",
  carry_choice: null,
  done_at: null,
  blocks_done: null,
  days_done: null,
  last_worked: null,
  days_missed: null,
  days_left: null,
  closeable: null,
  created_at: "2025-01-01T09:00:00+00:00",
};

beforeEach(() => {
  posted.length = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://x");
      const json = (body: unknown, status = 200) =>
        new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
      if (url.pathname === "/api/sprints") return json([ACTIVE, COMPLETED, PLANNED]);
      if (url.pathname === "/api/sprints/s-old")
        return json({ ...COMPLETED, tasks: [CARD, { ...CARD, id: "c-done", title: "Finished card", status: "done" }] });
      if (url.pathname === "/api/sprints/s-plan" && init?.method === "PATCH") {
        posted.push({ url: url.pathname, method: "PATCH", body: JSON.parse(String(init?.body)) });
        return json({ ...PLANNED, status: "active" });
      }
      if (url.pathname.endsWith("/carry-choice") || url.pathname.endsWith("/carry-choice-all")) {
        posted.push({ url: url.pathname, method: String(init?.method), body: JSON.parse(String(init?.body)) });
        return json({ ...CARD, carry_choice: "moved" });
      }
      return json([]);
    })
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <SprintList />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("SprintList", () => {
  it("shows the live sprint and the completed special with its ! badge", async () => {
    renderList();
    await screen.findByTestId("sprint.row-s-act");

    expect(screen.getByTestId("sprint.row-s-old")).toBeInTheDocument();
    expect(screen.getByTestId("sprint.fate-badge-s-old")).toHaveTextContent("!");
    expect(screen.getByTestId("sprint.archive-link")).toBeInTheDocument();
  });

  it("the card of a completed sprint is read-only and offers the fate menu", async () => {
    renderList();
    await userEvent.click(await screen.findByTestId("sprint.row-open-s-old"));

    const menu = await screen.findByTestId("sprint.fate-c-1");
    expect(screen.getByTestId("sprint.tasks-zone")).toBeInTheDocument();
    // DF29: the zone speaks as a question, not as an abstract command
    expect(screen.getByTestId("sprint.fate-question")).toHaveTextContent(
      "Перенести их в другой спринт?",
    );

    // "Без спринта" -> target_sprint_id: null (copy to the shelf, A40)
    await userEvent.selectOptions(menu, "shelf");
    await waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0].body).toEqual({ target_sprint_id: null });
  });

  it("a finished card of a closed sprint gets no fate menu (DF29/DF30)", async () => {
    // CARD in fixtures is planned (unfinished); add its finished twin below
    // the zone and assert the menu stays away from it.
    renderList();
    await userEvent.click(await screen.findByTestId("sprint.row-open-s-old"));
    await screen.findByTestId("sprint.fate-c-1");

    expect(screen.queryByTestId("sprint.fate-c-done")).not.toBeInTheDocument();
    // the finished card is still listed for information
    expect(screen.getByTestId("sprint.task-open-c-done")).toHaveTextContent("Finished card");
  });

  it("a planned row activates from the list itself (DF21)", async () => {
    renderList();
    const button = await screen.findByTestId("sprint.row-activate-s-plan");

    await userEvent.click(button);

    await waitFor(() =>
      expect(
        posted.some((p) => p.method === "PATCH" && (p.body as { status?: string }).status === "active"),
      ).toBe(true),
    );
  });
});
