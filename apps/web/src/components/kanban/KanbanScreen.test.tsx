import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { TaskDto } from "@/api/client";
import { KanbanScreen } from "./KanbanScreen";

/**
 * Screen level (render + data flow): fetch is stubbed at the transport so
 * the real client/hook/mutation wiring is exercised. Drag physics is
 * dnd-kit's own tested code; our rules around it live in board.test.ts.
 */

function task(overrides: Partial<TaskDto> = {}): TaskDto {
  return {
    id: "t-1",
    title: "Write tests",
    type: "normal",
    important: false,
    urgent: false,
    status: "backlog",
    estimate_blocks: 1,
    recurrence: { kind: "once" },
    deadline: null,
    parent_id: null,
    when_then: null,
    done_criteria: null,
    benefit: null,
    cloned_from: null,
    no_timer: false,
    blocks_done: null,
    last_worked: null,
    created_at: `${new Date().toLocaleDateString("en-CA")}T09:00:00+00:00`,
    ...overrides,
  };
}

let frogId: string | null = null;

const BOARD: TaskDto[] = [
  task({ id: "a", title: "Backlog card" }),
  task({ id: "b", title: "Planned card", status: "planned", estimate_blocks: 2 }),
  task({ id: "c", title: "Doing card", status: "doing", estimate_blocks: 2, when_then: "если 9:00 → пишу" }),
  task({ id: "d", title: "Done card", status: "done" }),
];

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  frogId = null;
  SPRINTS = [];
  fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.startsWith("/api/tasks")) {
      return jsonResponse(200, BOARD);
    }
    if (url.startsWith("/api/day-plans/")) {
      return jsonResponse(200, { id: "p", date: "2026-09-05", slots: [] });
    }
    if (url === "/api/frog") {
      return jsonResponse(200, { task_id: frogId });
    }
    if (url === "/api/settings") {
      return jsonResponse(200, SETTINGS_ON);
    }
    if (url === "/api/sprints") {
      return jsonResponse(200, SPRINTS);
    }
    throw new Error(`unexpected fetch: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
});

let SPRINTS: unknown[] = [];

const SETTINGS_ON = {
  session: {
    work_min: 25,
    break_min: 5,
    long_break_min: 15,
    long_break_every: 4,
    auto_start_next: true,
  },
  ui: { max_in_work: 6, theme: "auto", require_science_fields: false, wet_hints: true },
};

afterEach(() => {
  vi.unstubAllGlobals();
});

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function renderScreen() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <KanbanScreen />
    </QueryClientProvider>,
  );
}

describe("KanbanScreen", () => {
  it("renders four RU columns with cards grouped by status", async () => {
    renderScreen();

    await screen.findByTestId("task-card.root-a"); // data arrived
    expect(screen.getByTestId("kanban.column-backlog")).toHaveTextContent("Backlog card");
    expect(screen.getByTestId("kanban.column-planned")).toHaveTextContent("Planned card");
    expect(screen.getByTestId("kanban.column-doing")).toHaveTextContent("Doing card");
    expect(screen.getByTestId("kanban.column-done")).toHaveTextContent("Done card");
    // no archived lane leaks cards onto the board
    expect(screen.queryByText(/Archived/)).not.toBeInTheDocument();
  });

  it("shows card meta line on the face (type/quadrant/blocks)", async () => {
    renderScreen();

    await screen.findByTestId("task-card.root-b");
    expect(screen.getByTestId("task-card.type-b")).toHaveTextContent("Обычная");
    expect(screen.getByTestId("task-card.quadrant-b")).toHaveTextContent(
      "Не важно · не срочно",
    );
    expect(screen.getByTestId("task-card.blocks-b")).toHaveTextContent("2");
  });

  it("derives the day plan from the doing column (today = the dial)", async () => {
    renderScreen();

    const first = await screen.findByTestId("planner.slot-1");
    expect(first).toHaveTextContent("Doing card");
    expect(screen.getByTestId("planner.slot-2")).toHaveTextContent("Doing card");
    expect(screen.queryByTestId("planner.slot-3")).not.toBeInTheDocument();
  });

  it("refuses a blocked delete and explains it in RU (DF1)", async () => {
    const user = userEvent.setup();
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/tasks/a" && init?.method === "DELETE") {
        return jsonResponse(409, {
          detail: { code: "conflict", message: "task 'a' is planned on ['2026-09-10']" },
        });
      }
      if (url.startsWith("/api/tasks")) return jsonResponse(200, BOARD);
      if (url.startsWith("/api/day-plans/")) {
        return jsonResponse(200, { id: "p", date: "2026-09-05", slots: [] });
      }
      if (url === "/api/frog") return jsonResponse(200, { task_id: frogId });
      if (url === "/api/sprints") return jsonResponse(200, []);
      throw new Error(`unexpected fetch: ${url}`);
    });
    renderScreen();

    await user.click(await screen.findByTestId("task-card.edit-a"));
    await user.click(await screen.findByTestId("task-panel.delete-a"));

    expect(await screen.findByTestId("kanban.conflict-toast")).toHaveTextContent("стоит в плане");
  });

  it("duplicates a done card via POST clone (DF12)", async () => {
    const user = userEvent.setup();
    const posts: string[] = [];
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://x");
      if (url.pathname === "/api/tasks/d/clone" && init?.method === "POST") {
        posts.push(url.pathname);
        return jsonResponse(201, task({ id: "clone-x", status: "backlog", cloned_from: "d" }));
      }
      if (url.pathname === "/api/tasks") return jsonResponse(200, BOARD);
      if (url.pathname.startsWith("/api/day-plans/")) {
        return jsonResponse(200, { id: "p", date: "2026-09-05", slots: [] });
      }
      if (url.pathname === "/api/frog") return jsonResponse(200, { task_id: frogId });
      if (url.pathname === "/api/sprints") return jsonResponse(200, []);
      throw new Error(`unexpected fetch: ${url}`);
    });
    renderScreen();

    await user.click(await screen.findByTestId("task-card.edit-d"));
    await user.click(await screen.findByTestId("task-panel.clone-d"));

    expect(posts).toEqual(["/api/tasks/d/clone"]);
  });

  it("creates a task from the quick-add form via POST", async () => {
    const user = userEvent.setup();
    fetchMock.mockImplementation(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url === "/api/tasks" && init?.method === "POST") {
          return jsonResponse(201, task({ id: "new-1", title: "Fresh card" }));
        }
        if (url.startsWith("/api/tasks")) return jsonResponse(200, BOARD);
        if (url.startsWith("/api/settings")) {
          return jsonResponse(200, {
            session: {
              work_min: 25,
              break_min: 5,
              long_break_min: 15,
              long_break_every: 4,
              auto_start_next: true,
            },
            ui: { max_in_work: 12, theme: "auto" },
          });
        }
        if (url === "/api/sprints") return jsonResponse(200, []);
        return jsonResponse(200, { id: "p", date: "2026-09-05", slots: [] });
      },
    );
    renderScreen();
    await screen.findByTestId("kanban.column-backlog");

    await user.type(screen.getByTestId("kanban.create-input"), "Fresh card");
    await user.click(screen.getByTestId("kanban.create-submit"));

    await waitFor(() => {
      const post = fetchMock.mock.calls.find(
        ([url, init]) => url === "/api/tasks" && (init as RequestInit)?.method === "POST",
      );
      expect(post).toBeTruthy();
      const body = JSON.parse(String((post![1] as RequestInit).body));
      expect(body.title).toBe("Fresh card");
      expect(body.id).toMatch(/^task-/);
    });
  });

  it("ticks sprint days via the panel and PATCHes on_dates (DF8)", async () => {
    const user = userEvent.setup();
    // Stateful mock: PATCH mutates the live list and GET returns it — the
    // second tick must build on the card the server already saved.
    const live = BOARD.map((t) => ({ ...t }));
    const sprint = {
      id: "s-1",
      number: 1,
      name: "w37",
      goal: null,
      done_criteria: null,
      start_date: "2026-09-07",
      end_date: "2026-09-13",
      status: "active",
    };
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = String(init?.method ?? "GET").toUpperCase();
      if (url === "/api/tasks" && method === "GET") return jsonResponse(200, live);
      const patchMatch = /^\/api\/tasks\/([\w-]+)$/.exec(url);
      if (patchMatch && method === "PATCH") {
        const card = live.find((t) => t.id === patchMatch[1]);
        if (!card) return jsonResponse(404, { detail: "gone" });
        Object.assign(card, JSON.parse(String(init?.body)));
        return jsonResponse(200, card);
      }
      if (url.startsWith("/api/day-plans/")) {
        return jsonResponse(200, { id: "p", date: "2026-09-05", slots: [] });
      }
      if (url === "/api/frog") return jsonResponse(200, { task_id: frogId });
      if (url === "/api/settings") return jsonResponse(200, SETTINGS_ON);
      if (url === "/api/sprints") return jsonResponse(200, [sprint]);
      throw new Error(`unexpected fetch: ${url}`);
    });
    renderScreen();

    await user.click(await screen.findByTestId("task-card.edit-a"));
    await user.click(await screen.findByTestId("task-panel.day-a-2026-09-09"));
    await waitFor(() =>
      expect(screen.getByTestId("task-panel.day-a-2026-09-09")).toHaveAttribute(
        "aria-pressed",
        "true",
      )
    );
    await user.click(screen.getByTestId("task-panel.day-a-2026-09-11"));

    await waitFor(() => {
      const patches = fetchMock.mock.calls
        .filter(
          ([url, init]) => url === "/api/tasks/a" && (init as RequestInit)?.method === "PATCH",
        )
        .map(([, init]) => JSON.parse(String((init as RequestInit).body)) as Record<string, unknown>);
      expect(patches.at(-1)?.recurrence).toEqual({
        kind: "on_dates",
        days: ["2026-09-09", "2026-09-11"],
      });
    });
  });

  it("hides last week's done cards under 'This week' and brings them back (DF3-filter)", async () => {
    const user = userEvent.setup();
    const oldDone = {
      ...task({ id: "old" }),
      status: "done" as const,
      created_at: "2020-01-02T09:00:00+00:00",
      last_worked: "2020-01-03",
    };
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.startsWith("/api/tasks")) return jsonResponse(200, [...BOARD, oldDone]);
      if (url.startsWith("/api/day-plans/")) {
        return jsonResponse(200, { id: "p", date: "2026-09-05", slots: [] });
      }
      if (url === "/api/frog") return jsonResponse(200, { task_id: frogId });
      if (url === "/api/settings") return jsonResponse(200, SETTINGS_ON);
      if (url === "/api/sprints") return jsonResponse(200, []);
      throw new Error(`unexpected fetch: ${url}`);
    });
    renderScreen();
    await screen.findByTestId("task-card.root-a");

    expect(screen.queryByTestId("task-card.root-old")).not.toBeInTheDocument();
    // today's Done card survives: it belongs to this week
    expect(screen.getByTestId("task-card.root-d")).toBeInTheDocument();

    await user.click(screen.getByTestId("kanban.filter-all"));

    expect(await screen.findByTestId("task-card.root-old")).toBeInTheDocument();
  });

  it("shows the done/total dot row for a ticked card (DF10)", async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.startsWith("/api/tasks")) {
        return jsonResponse(
          200,
          [
            {
              ...task({ id: "r" }),
              recurrence: {
                kind: "on_dates",
                days: ["2026-09-09", "2026-09-10", "2026-09-11"],
              },
              blocks_done: 2,
            },
          ],
        );
      }
      if (url.startsWith("/api/day-plans/")) {
        return jsonResponse(200, { id: "p", date: "2026-09-05", slots: [] });
      }
      if (url === "/api/frog") return jsonResponse(200, { task_id: null });
      if (url === "/api/settings") return jsonResponse(200, SETTINGS_ON);
      if (url === "/api/sprints") return jsonResponse(200, []);
      throw new Error(`unexpected fetch: ${url}`);
    });
    renderScreen();

    const dots = await screen.findByTestId("task-card.progress-r");
    expect(dots).toHaveTextContent("2/3");
    expect(dots).toHaveAccessibleName("Прогресс: 2 из 3");
  });

  it("arrows reorder the dial plan as whole blocks (DF4-lite)", async () => {
    const user = userEvent.setup();
    const doing = [
      task({ id: "c", title: "Doing card", status: "doing", estimate_blocks: 2 }),
      task({ id: "x", title: "Second doing", status: "doing", estimate_blocks: 1 }),
    ];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.startsWith("/api/day-plans/") && init?.method === "PUT") {
          return jsonResponse(200, JSON.parse(String(init.body)) as { id: string });
        }
        if (url.startsWith("/api/tasks")) return jsonResponse(200, doing);
        if (url.startsWith("/api/day-plans/"))
          return jsonResponse(200, { id: "p", date: "2026-09-08", slots: [] });
        if (url === "/api/frog") return jsonResponse(200, { task_id: null, reason: null });
        if (url === "/api/settings/ui") return jsonResponse(200, { ui: { theme: "auto" } });
        if (url === "/api/sprints") return jsonResponse(200, []);
        return jsonResponse(404, { error: { code: "not_found", message: url } });
      }),
    );
    render(<QueryClientProvider client={new QueryClient()}><KanbanScreen /></QueryClientProvider>);
    // column order c(2 blocks) + x(1): sectors c,c,x — row shows both.
    const order = await screen.findByTestId("kanban.planner-order");
    expect(within(order).getByTestId("planner.order-c")).toBeTruthy();
    await user.click(within(order).getByTestId("planner.order-up-x"));
    await waitFor(() => {
      const put = (fetch as ReturnType<typeof vi.fn>).mock.calls
        .map(([url, init]) => ({ url: String(url), init: init as RequestInit | undefined }))
        .find((call) => call.url.startsWith("/api/day-plans/") && call.init?.method === "PUT");
      expect(put).toBeTruthy();
      const body = JSON.parse(String(put?.init?.body)) as { slots: { task_id: string }[] };
      // the whole x block jumped over the whole c block: x,c,c
      expect(body.slots.map((s) => s.task_id)).toEqual(["x", "c", "c"]);
    });
  });

  it("opens the side panel for ONE card (DF2 replaces column-wide edit)", async () => {
    const user = userEvent.setup();
    renderScreen();
    await screen.findByTestId("task-card.root-a");

    await user.click(screen.getByTestId("task-card.edit-a"));

    const panel = await screen.findByTestId("task-panel.root-a");
    expect(panel).toBeInTheDocument();
    expect(screen.getByTestId("task-panel.title-a")).toHaveValue("Backlog card");
    expect(screen.getByTestId("task-panel.quadrant-a")).toBeInTheDocument();
    // the other card never gets a form: editing is per-card now
    expect(screen.queryByTestId("task-panel.root-c")).not.toBeInTheDocument();

    await user.click(screen.getByTestId("task-panel.close"));
    expect(screen.queryByTestId("task-panel.root-a")).not.toBeInTheDocument();
  });

  it("Esc closes the card panel (U2 overlay law)", async () => {
    const user = userEvent.setup();
    renderScreen();
    await screen.findByTestId("task-card.root-a");

    await user.click(screen.getByTestId("task-card.edit-a"));
    await screen.findByTestId("task-panel.root-a");
    await user.keyboard("{Escape}");

    expect(screen.queryByTestId("task-panel.root-a")).not.toBeInTheDocument();
  });

  it("wet-hint marks only scheduled cards with a blank when_then", async () => {
    renderScreen();
    await screen.findByTestId("task-card.root-b");

    expect(screen.getByTestId("task-card.wt-hint-b")).toBeInTheDocument(); // planned, blank
    expect(screen.queryByTestId("task-card.wt-hint-c")).not.toBeInTheDocument(); // has when_then
    expect(screen.queryByTestId("task-card.wt-hint-a")).not.toBeInTheDocument(); // backlog: no ring
    expect(screen.queryByTestId("task-card.wt-hint-d")).not.toBeInTheDocument(); // done: no ring
  });

  it("wet-hint rings switch off when the server says so (DF6)", async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/settings") {
        return jsonResponse(200, {
          ...SETTINGS_ON,
          ui: { ...SETTINGS_ON.ui, wet_hints: false },
        });
      }
      if (url.startsWith("/api/tasks")) return jsonResponse(200, BOARD);
      if (url.startsWith("/api/day-plans/")) {
        return jsonResponse(200, { id: "p", date: "2026-09-05", slots: [] });
      }
      if (url === "/api/frog") return jsonResponse(200, { task_id: frogId });
      if (url === "/api/sprints") return jsonResponse(200, []);
      throw new Error(`unexpected fetch: ${url}`);
    });
    renderScreen();
    await screen.findByTestId("task-card.root-b");

    expect(screen.queryByTestId("task-card.wt-hint-b")).not.toBeInTheDocument();
  });

  it("frog badge lights the server-computed candidate", async () => {
    frogId = "b";
    renderScreen();
    await screen.findByTestId("task-card.root-b");

    expect(screen.getByTestId("task-card.frog-badge-b")).toBeInTheDocument();
    expect(screen.queryByTestId("task-card.frog-badge-a")).not.toBeInTheDocument();
    frogId = null;
  });

  it("wet-hint stays on the card face while its panel is open (DF2)", async () => {
    const user = userEvent.setup();
    renderScreen();
    await screen.findByTestId("task-card.wt-hint-b");

    await user.click(screen.getByTestId("task-card.edit-b"));

    expect(screen.getByTestId("task-card.wt-hint-b")).toBeInTheDocument();
    expect(screen.getByTestId("task-panel.root-b")).toBeInTheDocument();
  });
});
